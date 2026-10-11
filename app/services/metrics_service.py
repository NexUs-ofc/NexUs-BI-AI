"""Metrics report: turns the per-question documents into the requested indicators.

- Estimated cost for 100 and 1000 weekly users
- Inter-agent latency (each graph node) and total response time
- Error rate
- Cost per resolution (a question is resolved when the judge approved a specialist answer)
- ROI = (savings - cost) / cost, where savings = resolved questions x minutes saved x analyst hour
"""
import math
from datetime import datetime, timedelta, timezone

from app.observability.cost import get_usd_to_brl
from app.repository.metrics_repository import find_metrics_since, find_tool_calls_since
from app.schemas.metrics import LatencyStats, MetricsReport, Scenario, ToolStats

# Default assumptions (they can be changed in the query string of /metrics/report)
QUESTIONS_PER_USER_WEEK = 10
MINUTES_SAVED_PER_RESOLUTION = 10
ANALYST_HOUR_BRL = 50.0
SCENARIO_USERS = (100, 1000)
WEEKS_PER_MONTH = 52 / 12


def _latency(values: list[float]) -> LatencyStats:
    if not values:
        return LatencyStats(avg_ms=0, p95_ms=0)
    ordered = sorted(values)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    return LatencyStats(avg_ms=round(sum(values) / len(values), 1), p95_ms=round(p95, 1))


def _rate(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


def _roi(savings: float, cost: float) -> float | None:
    return round((savings - cost) / cost, 2) if cost > 0 else None


def _tool_stats(tool_calls: list[dict]) -> dict[str, ToolStats]:
    by_tool: dict[str, list[dict]] = {}
    for call in tool_calls:
        by_tool.setdefault(call["tool_name"], []).append(call)
    stats = {}
    for name, calls in by_tool.items():
        latency = _latency([c["duration_ms"] for c in calls])
        errors = sum(not c["success"] for c in calls)
        stats[name] = ToolStats(calls=len(calls), error_rate=_rate(errors, len(calls)), avg_ms=latency.avg_ms, p95_ms=latency.p95_ms)
    return stats


def build_report(
    days: int = 7,
    questions_per_user_week: int = QUESTIONS_PER_USER_WEEK,
    minutes_saved_per_resolution: float = MINUTES_SAVED_PER_RESOLUTION,
    analyst_hour_brl: float = ANALYST_HOUR_BRL,
) -> MetricsReport:
    usd_to_brl, rate_source = get_usd_to_brl()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    docs = find_metrics_since(since)
    total = len(docs)
    resolved = sum(d["resolved"] for d in docs)

    # Cost
    total_cost_brl = sum(d["cost_usd"] for d in docs) * usd_to_brl
    avg_cost_brl = total_cost_brl / total if total else 0.0
    saving_per_resolution = minutes_saved_per_resolution / 60 * analyst_hour_brl
    savings_brl = resolved * saving_per_resolution

    # Latency of each node (inter-agent) and total
    by_node: dict[str, list[float]] = {}
    for d in docs:
        for node, ms in d.get("latency_by_node_ms", {}).items():
            by_node.setdefault(node, []).append(ms)

    # Scenarios: same average cost and resolution rate, more users
    scenarios = []
    for users in SCENARIO_USERS:
        weekly_questions = users * questions_per_user_week
        weekly_cost = weekly_questions * avg_cost_brl
        weekly_savings = weekly_questions * _rate(resolved, total) * saving_per_resolution
        scenarios.append(Scenario(
            weekly_users=users,
            weekly_questions=weekly_questions,
            weekly_cost_brl=round(weekly_cost, 2),
            monthly_cost_brl=round(weekly_cost * WEEKS_PER_MONTH, 2),
            weekly_savings_brl=round(weekly_savings, 2),
            roi=_roi(weekly_savings, weekly_cost),
        ))

    return MetricsReport(
        period_days=days,
        questions=total,
        resolved=resolved,
        resolution_rate=_rate(resolved, total),
        error_rate=_rate(sum(d["error"] for d in docs), total),
        judge_rejection_rate=_rate(sum(d["judge_rejected"] for d in docs), total),
        blocked_rate=_rate(sum(d["blocked"] for d in docs), total),
        latency_total=_latency([d["latency_total_ms"] for d in docs]),
        latency_by_node={node: _latency(values) for node, values in by_node.items()},
        tools=_tool_stats(find_tool_calls_since(since)),
        input_tokens=sum(d["input_tokens"] for d in docs),
        output_tokens=sum(d["output_tokens"] for d in docs),
        total_cost_brl=round(total_cost_brl, 4),
        avg_cost_per_question_brl=round(avg_cost_brl, 6),
        cost_per_resolution_brl=round(total_cost_brl / resolved, 6) if resolved else None,
        savings_brl=round(savings_brl, 2),
        roi=_roi(savings_brl, total_cost_brl),
        scenarios=scenarios,
        assumptions={
            "questions_per_user_week": questions_per_user_week,
            "minutes_saved_per_resolution": minutes_saved_per_resolution,
            "analyst_hour_brl": analyst_hour_brl,
            "usd_to_brl": usd_to_brl,
        },
        usd_to_brl_source=rate_source,
    )
