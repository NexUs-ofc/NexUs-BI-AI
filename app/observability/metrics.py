"""Metrics collected while the graph runs and saved in MongoDB (see repository/metrics_repository.py).

- metrics_bi: one document per question with route, whether it was resolved, blocked or rejected by the
  judge, errors, total latency and latency of each graph node, Gemini tokens and estimated cost.
- tool_metrics_bi: one document per tool call, collected by ToolMetricsCallback (LangChain callback).
Both share the trace_id of the question. services/metrics_service.py turns them into the report.
"""
import functools
import time
import uuid
from datetime import UTC, datetime

from langchain_core.callbacks import BaseCallbackHandler

from app.config import LLM_MODEL
from app.model.llm import is_quota_error
from app.observability.cost import estimate_cost_usd
from app.repository.metrics_repository import save_metric, save_tool_calls

SPECIALIST_ROUTES = {"faq", "analyst", "recommender"}


def timed(node_name: str):
    """Decorator for graph nodes: adds how long the node took to the "timings" field of the state."""

    def decorator(node):
        @functools.wraps(node)
        def run(state):
            start = time.perf_counter()
            update = node(state)
            update["timings"] = [{"node": node_name, "ms": (time.perf_counter() - start) * 1000}]
            return update

        return run

    return decorator


def new_trace_id() -> str:
    return uuid.uuid4().hex


class ToolMetricsCallback(BaseCallbackHandler):
    """LangChain calls these methods whenever any agent runs a tool; we keep one record per call."""

    def __init__(self, trace_id: str):
        super().__init__()
        self.trace_id = trace_id
        self.tool_calls: list[dict] = []
        self._running: dict = {}  # run_id -> (tool name, start datetime, start perf counter)

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        name = kwargs.get("name") or (serialized or {}).get("name", "unknown")
        self._running[run_id] = (name, datetime.now(UTC), time.perf_counter())

    def on_tool_end(self, output, *, run_id, **kwargs):
        self._finish(run_id, success=True)

    def on_tool_error(self, error, *, run_id, **kwargs):
        self._finish(run_id, success=False)

    def _finish(self, run_id, success: bool) -> None:
        name, started_at, started_perf = self._running.pop(
            run_id, ("unknown", datetime.now(UTC), time.perf_counter())
        )
        self.tool_calls.append({
            "trace_id": self.trace_id,
            "tool_name": name,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "duration_ms": (time.perf_counter() - started_perf) * 1000,
            "success": success,
        })


def _latency_by_node(timings: list[dict]) -> dict[str, float]:
    """Sum the time of each node (specialist and judge may run more than once)."""
    total: dict[str, float] = {}
    for item in timings:
        total[item["node"]] = total.get(item["node"], 0.0) + item["ms"]
    return {node: round(ms, 1) for node, ms in total.items()}


def record_question(
    trace_id: str,
    state: dict | None,
    started: float,
    usage_by_model: dict,
    tool_calls: list[dict],
    error: Exception | None,
) -> None:
    """Save the question metric and its tool calls. Never breaks the chat."""
    state = state or {}
    route = state.get("route", "error" if error else "")
    approved = bool(state.get("approved"))
    document = {
        "trace_id": trace_id,
        "created_at": datetime.now(UTC),
        "route": route,
        "resolved": error is None and route in SPECIALIST_ROUTES and approved,
        "blocked": route == "blocked",
        "output_blocked": bool(state.get("output_blocked")),
        "judge_rejected": error is None and route in SPECIALIST_ROUTES and not approved,
        "attempts": state.get("attempts", 0),
        "tool_calls": len(tool_calls),
        "error": error is not None,
        "error_type": type(error).__name__ if error else None,
        "quota_error": is_quota_error(error),
        "latency_total_ms": round((time.perf_counter() - started) * 1000, 1),
        "latency_by_node_ms": _latency_by_node(state.get("timings", [])),
        "input_tokens": sum(u.get("input_tokens", 0) for u in usage_by_model.values()),
        "output_tokens": sum(u.get("output_tokens", 0) for u in usage_by_model.values()),
        "cost_usd": estimate_cost_usd(usage_by_model),
        "model": LLM_MODEL,
    }
    try:
        save_metric(document)
        save_tool_calls(tool_calls)
    except Exception as e:  # noqa: BLE001 - metrics must never break the answer
        print(f"[metrics] ATENÇÃO: não foi possível salvar a métrica: {e}")
