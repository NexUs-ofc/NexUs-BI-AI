"""LangSmith section of the admin panel: runs and errors per day, latency per chain and per agent, feedback.

It pages the LangSmith API, so it is slow and lives apart from the rest of the page. Without LangSmith
(no key, tracing off, API down) it answers "disponivel": false instead of failing the panel.

The graph nodes are LangSmith runs (@traceable), so the chain latency comes from there. The specialists
are one node with three routes, which LangSmith does not tell apart: the per-agent latency comes from the
"specialist" time saved in metrics_bi, split by route.
"""
import math
import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from langsmith import Client

from app.config import BRAZIL_TZ
from app.repository.metrics_repository import find_metrics_between

ROOT_RUN = "orchestrator"
CHAIN_RUNS = ("input_guardrail", "router", "specialist", "judge", "finish")
AGENT_ROUTES = ("faq", "analyst", "recommender")
MAX_RUNS = 10_000


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _duration(run) -> float | None:
    if not run.start_time or not run.end_time:
        return None
    return (run.end_time - run.start_time).total_seconds()


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def runs_per_day(roots: list) -> list[dict]:
    days: dict[str, dict] = {}
    for run in roots:
        if not run.start_time:
            continue
        day = _utc(run.start_time).astimezone(BRAZIL_TZ).date().isoformat()
        row = days.setdefault(day, {"dia": day, "execucoes": 0, "erros": 0})
        row["execucoes"] += 1
        row["erros"] += run.status == "error"
    for row in days.values():
        row["taxa_erro_pct"] = round(row["erros"] / row["execucoes"] * 100, 2)
    return sorted(days.values(), key=lambda row: row["dia"])


def latency_by_name(runs: list, names: tuple[str, ...]) -> list[dict]:
    by_name: dict[str, list[float]] = defaultdict(list)
    for run in runs:
        duration = _duration(run)
        if run.name in names and duration is not None:
            by_name[run.name].append(duration)
    return [
        {
            "nome": name,
            "chamadas": len(values),
            "p50_s": round(_percentile(values, 0.50), 2),
            "p99_s": round(_percentile(values, 0.99), 2),
        }
        for name, values in sorted(by_name.items())
    ]


def latency_by_agent(docs: list[dict]) -> list[dict]:
    by_route: dict[str, list[float]] = defaultdict(list)
    for doc in docs:
        specialist_ms = (doc.get("latency_by_node_ms") or {}).get("specialist")
        if doc.get("route") in AGENT_ROUTES and specialist_ms is not None:
            by_route[doc["route"]].append(specialist_ms / 1000)
    return [
        {
            "nome": route,
            "chamadas": len(values),
            "p50_s": round(_percentile(values, 0.50), 2),
            "p99_s": round(_percentile(values, 0.99), 2),
        }
        for route, values in sorted(by_route.items())
    ]


def feedback(roots: list) -> dict:
    """Sum of the feedback stats LangSmith keeps on each root run. No feedback = total 0, not an empty average."""
    by_key: dict[str, dict] = {}
    for run in roots:
        for key, stats in (run.feedback_stats or {}).items():
            count = int(stats.get("n") or 0)
            if not count:
                continue
            row = by_key.setdefault(key, {"avaliacoes": 0, "soma": 0.0})
            row["avaliacoes"] += count
            row["soma"] += float(stats.get("avg") or 0.0) * count
    return {
        "disponivel": True,
        "total": sum(row["avaliacoes"] for row in by_key.values()),
        "por_chave": {
            key: {"avaliacoes": row["avaliacoes"], "media": round(row["soma"] / row["avaliacoes"], 3)}
            for key, row in by_key.items()
        },
    }


def build_langsmith(days: int = 7) -> dict:
    project = os.environ.get("LANGSMITH_PROJECT", "ceris-ms-ia-bi")
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    agents = latency_by_agent(find_metrics_between(start, end))

    try:
        client = Client()
        roots = list(client.list_runs(project_name=project, start_time=start, is_root=True, limit=MAX_RUNS))
        chains = list(client.list_runs(
            project_name=project,
            start_time=start,
            filter=f"in(name, {list(CHAIN_RUNS)!r})".replace("'", '"'),
            limit=MAX_RUNS,
        ))
    except Exception as e:  # noqa: BLE001 - the panel shows the section as unavailable
        return {
            "projeto": project,
            "disponivel": False,
            "erro": f"{type(e).__name__}: {str(e)[:200]}",
            "latencia_por_agente": agents,
        }

    roots = [run for run in roots if run.name == ROOT_RUN] or roots
    return {
        "projeto": project,
        "disponivel": True,
        "periodo": {"inicio": start.isoformat(timespec="seconds"), "fim": end.isoformat(timespec="seconds")},
        "execucoes_por_dia": runs_per_day(roots),
        "latencia_por_chain": latency_by_name(chains, CHAIN_RUNS),
        "latencia_por_agente": agents,
        "feedback": feedback(roots),
    }
