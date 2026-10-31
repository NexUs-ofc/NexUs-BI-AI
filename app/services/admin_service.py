"""Admin panel data: the BI IA page, built from the documents the graph already saves in MongoDB.

The JSON keys are in Portuguese and match the IA page of NexUs-AI on purpose: the panel draws both pages
with the same components. What does not exist here comes as null (receipt reading) or zero (the judge's
second opinion, which only NexUs-AI has).

- metrics_bi: one document per question (route, attempts, approved, latency per node, tokens, cost...)
- tool_metrics_bi: one document per tool call
The LangSmith section is separate (build_langsmith) because it pages a remote API and is slow.
"""
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from app.config import BRAZIL_TZ, DAILY_TOKEN_LIMIT, LLM_MODEL
from app.repository.metrics_repository import (
    find_metrics_between,
    find_tool_calls_between,
)

SPECIALIST_ROUTES = {"faq", "analyst", "recommender"}

# Graph nodes grouped into the stages the panel stacks. "finish" runs the output guardrail.
NODE_STAGE = {
    "input_guardrail": "guardrails",
    "finish": "guardrails",
    "router": "roteador",
    "specialist": "agente",
    "judge": "juiz",
}
STAGES = ("roteador", "agente", "juiz", "guardrails", "orquestrador")
JUDGE_DECISIONS = ("aprovado", "devolvido", "revertido")


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _pct(part: float, total: float) -> float:
    return round(part / total * 100, 2) if total else 0.0


def _seconds(ms: float) -> float:
    return round(ms / 1000, 2)


def _utc(moment: datetime) -> datetime:
    """pymongo returns naive datetimes in UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _day(moment: datetime) -> str:
    return _utc(moment).astimezone(BRAZIL_TZ).date().isoformat()


def _window_days(start: datetime, end: datetime) -> list[str]:
    first = _utc(start).astimezone(BRAZIL_TZ).date()
    last = _utc(end).astimezone(BRAZIL_TZ).date()
    return [(first + timedelta(days=n)).isoformat() for n in range((last - first).days + 1)]


def judge_decisions(doc: dict) -> list[str]:
    """One decision per judge run, rebuilt from attempts and the final verdict.

    Every specialist attempt is judged once. Rejected attempts were sent back ("devolvido"); the last one
    is "aprovado" when the question was resolved. Out of scope and blocked questions never reach the judge.
    """
    attempts = int(doc.get("attempts") or 0)
    if doc.get("route") not in SPECIALIST_ROUTES or attempts == 0:
        return []
    if doc.get("resolved"):
        return ["devolvido"] * (attempts - 1) + ["aprovado"]
    return ["devolvido"] * attempts


def summary(docs: list[dict]) -> dict:
    durations = [d.get("latency_total_ms", 0.0) for d in docs]
    decisions = [x for d in docs for x in judge_decisions(d)]
    return {
        "execucoes": len(docs),
        "p50_e2e_s": _seconds(_percentile(durations, 0.50)),
        "p95_e2e_s": _seconds(_percentile(durations, 0.95)),
        "custo_usd": round(sum(d.get("cost_usd", 0.0) for d in docs), 4),
        "taxa_erro_pct": _pct(sum(1 for d in docs if d.get("error")), len(docs)),
        "devolucoes_juiz_pct": _pct(decisions.count("devolvido"), len(decisions)),
    }


def latency_by_route(docs: list[dict]) -> list[dict]:
    by_route: dict[str, list[dict]] = defaultdict(list)
    for doc in docs:
        by_route[doc.get("route") or "desconhecida"].append(doc)
    rows = []
    for route, items in by_route.items():
        durations = [d.get("latency_total_ms", 0.0) for d in items]
        rows.append({
            "rota": route,
            "execucoes": len(items),
            "erros": sum(1 for d in items if d.get("error")),
            "p50_s": _seconds(_percentile(durations, 0.50)),
            "p95_s": _seconds(_percentile(durations, 0.95)),
        })
    return sorted(rows, key=lambda row: row["p95_s"], reverse=True)


def latency_by_stage(docs: list[dict]) -> list[dict]:
    """Average seconds of each stage per route: the stages add up to the average end-to-end time."""
    by_route: dict[str, list[dict[str, float]]] = defaultdict(list)
    for doc in docs:
        stages: dict[str, float] = defaultdict(float)
        for node, ms in (doc.get("latency_by_node_ms") or {}).items():
            if node in NODE_STAGE:
                stages[NODE_STAGE[node]] += ms
        if stages:
            by_route[doc.get("route") or "desconhecida"].append(stages)
    rows = []
    for route, runs in by_route.items():
        averages = {stage: _seconds(sum(r.get(stage, 0.0) for r in runs) / len(runs)) for stage in STAGES}
        rows.append({
            "rota": route,
            "execucoes": len(runs),
            "etapas_s": averages,
            "total_s": round(sum(averages.values()), 2),
        })
    return sorted(rows, key=lambda row: row["total_s"], reverse=True)


def tokens_by_day(docs: list[dict], start: datetime, end: datetime) -> dict:
    days = {day: {"dia": day, "entrada": 0, "saida": 0, "total": 0, "por_rota": {}} for day in _window_days(start, end)}
    for doc in docs:
        row = days.get(_day(doc["created_at"]))
        if row is None:
            continue
        tokens_in = int(doc.get("input_tokens") or 0)
        tokens_out = int(doc.get("output_tokens") or 0)
        row["entrada"] += tokens_in
        row["saida"] += tokens_out
        row["total"] += tokens_in + tokens_out
        by_route = row["por_rota"].setdefault(doc.get("route") or "desconhecida", {"entrada": 0, "saida": 0})
        by_route["entrada"] += tokens_in
        by_route["saida"] += tokens_out
    rows = list(days.values())
    peak = max(rows, key=lambda row: row["total"]) if rows else None
    limit = DAILY_TOKEN_LIMIT or None
    return {
        "limite_diario": limit,
        "total_entrada": sum(row["entrada"] for row in rows),
        "total_saida": sum(row["saida"] for row in rows),
        "pico": {
            "dia": peak["dia"],
            "total": peak["total"],
            "pct_do_limite": _pct(peak["total"], limit) if limit else None,
        } if peak else None,
        "dias": rows,
    }


def cost_by_day(docs: list[dict], start: datetime, end: datetime) -> dict:
    days = {day: {"dia": day, "total_usd": 0.0, "por_modelo": {}} for day in _window_days(start, end)}
    by_model: dict[str, float] = defaultdict(float)
    for doc in docs:
        row = days.get(_day(doc["created_at"]))
        cost = float(doc.get("cost_usd") or 0.0)
        if row is None or not cost:
            continue
        model = doc.get("model") or LLM_MODEL
        row["total_usd"] += cost
        row["por_modelo"][model] = row["por_modelo"].get(model, 0.0) + cost
        by_model[model] += cost
    for row in days.values():
        row["total_usd"] = round(row["total_usd"], 6)
        row["por_modelo"] = {m: round(v, 6) for m, v in row["por_modelo"].items()}
    return {
        "total_usd": round(sum(by_model.values()), 6),
        "por_modelo": {m: round(v, 6) for m, v in by_model.items()},
        "dias": list(days.values()),
    }


def _is_quota(doc: dict) -> bool:
    # Documents saved before "quota_error" existed only have the exception name.
    return bool(doc.get("quota_error")) or doc.get("error_type") in {"ResourceExhausted", "RateLimitError"}


def quota_errors(docs: list[dict], end: datetime) -> dict:
    """Questions that ended in a Gemini quota error (429), hour by hour in the last 24h."""
    start = _utc(end) - timedelta(hours=24)
    hours = {}
    for n in range(24):
        hour = (start + timedelta(hours=n + 1)).astimezone(BRAZIL_TZ).replace(minute=0, second=0, microsecond=0)
        hours[hour.isoformat()] = 0
    total = 0
    for doc in docs:
        if not _is_quota(doc):
            continue
        total += 1
        moment = _utc(doc["created_at"])
        if moment > start:
            key = moment.astimezone(BRAZIL_TZ).replace(minute=0, second=0, microsecond=0).isoformat()
            if key in hours:
                hours[key] += 1
    return {
        "total_24h": sum(hours.values()),
        "total_janela": total,
        "por_hora": [{"hora": hour, "quantidade": n} for hour, n in hours.items()],
    }


def judge(docs: list[dict]) -> dict:
    decisions = [x for d in docs for x in judge_decisions(d)]
    total = len(decisions)
    return {
        "total": total,
        **{
            decision: {"quantidade": decisions.count(decision), "pct": _pct(decisions.count(decision), total)}
            for decision in JUDGE_DECISIONS
        },
    }


def guardrails(docs: list[dict]) -> dict:
    blocked_in = sum(1 for d in docs if d.get("blocked"))
    blocked_out = sum(1 for d in docs if d.get("output_blocked"))
    return {
        "execucoes": len(docs),
        "entrada": blocked_in,
        "saida": blocked_out,
        "total": blocked_in + blocked_out,
        "pct": _pct(blocked_in + blocked_out, len(docs)),
    }


def tools(calls: list[dict]) -> list[dict]:
    by_tool: dict[str, list[dict]] = defaultdict(list)
    for call in calls:
        by_tool[call.get("tool_name") or "desconhecida"].append(call)
    rows = []
    for name, items in by_tool.items():
        durations = [c.get("duration_ms", 0.0) for c in items]
        errors = sum(1 for c in items if not c.get("success", True))
        rows.append({
            "tool": name,
            "chamadas": len(items),
            "erros": errors,
            "taxa_erro_pct": _pct(errors, len(items)),
            "media_ms": round(sum(durations) / len(durations), 1),
            "p95_ms": round(_percentile(durations, 0.95), 1),
        })
    return sorted(rows, key=lambda row: row["chamadas"], reverse=True)


def _window(days: int, end: datetime | None) -> tuple[datetime, datetime]:
    end = end or datetime.now(UTC)
    return end - timedelta(days=days), end


def build_dashboard(days: int = 7, end: datetime | None = None) -> dict:
    """The BI IA page of the panel, minus the LangSmith section."""
    start, end = _window(days, end)
    docs = find_metrics_between(start, end)
    calls = find_tool_calls_between(start, end)
    return {
        "servico": "ceris-bi-ia",
        "janela": {
            "inicio": start.isoformat(timespec="seconds"),
            "fim": end.isoformat(timespec="seconds"),
            "dias": days,
        },
        "resumo": summary(docs),
        "desempenho": {
            "latencia_por_rota": latency_by_route(docs),
            "latencia_por_no": latency_by_stage(docs),
        },
        "leitura_nota": None,
        "custo": {
            "tokens": tokens_by_day(docs, start, end),
            "custo": cost_by_day(docs, start, end),
            "erros_de_cota": quota_errors(docs, end),
        },
        "qualidade": {
            "juiz": judge(docs),
            "guardrails": guardrails(docs),
            "ferramentas": tools(calls),
        },
    }


# (key, unit, change in percentage points instead of %)
INDICATORS = (
    ("volume", "execucoes", False),
    ("latencia_p95_e2e_s", "s", False),
    ("custo_usd", "usd", False),
    ("taxa_erro_pct", "%", True),
    ("devolucoes_juiz_pct", "%", True),
)


def _indicators(docs: list[dict]) -> dict:
    numbers = summary(docs)
    return {
        "volume": numbers["execucoes"],
        "latencia_p95_e2e_s": numbers["p95_e2e_s"],
        "custo_usd": numbers["custo_usd"],
        "taxa_erro_pct": numbers["taxa_erro_pct"],
        "devolucoes_juiz_pct": numbers["devolucoes_juiz_pct"],
    }


def _change(current: float, previous: float, in_points: bool) -> float | None:
    if in_points:
        return round(current - previous, 2)
    return round((current - previous) / previous * 100, 2) if previous else None


def build_period_report(days: int = 7, end: datetime | None = None) -> dict:
    """The period compared with the previous period of the same size (the panel's report button)."""
    start, end = _window(days, end)
    previous_start = start - timedelta(days=days)
    docs = find_metrics_between(start, end)
    previous = find_metrics_between(previous_start, start)
    calls = find_tool_calls_between(start, end)

    current_numbers = _indicators(docs)
    previous_numbers = _indicators(previous)
    failing_tools = sorted(
        (row for row in tools(calls) if row["erros"]),
        key=lambda row: (row["taxa_erro_pct"], row["chamadas"]),
        reverse=True,
    )
    tokens = tokens_by_day(docs, start, end)

    return {
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "periodo_atual": {"inicio": start.isoformat(timespec="seconds"), "fim": end.isoformat(timespec="seconds")},
        "periodo_anterior": {
            "inicio": previous_start.isoformat(timespec="seconds"),
            "fim": start.isoformat(timespec="seconds"),
        },
        "indicadores": [
            {
                "indicador": key,
                "unidade": unit,
                "atual": current_numbers[key],
                "anterior": previous_numbers[key],
                "variacao": _change(current_numbers[key], previous_numbers[key], in_points),
                "variacao_em": "pontos" if in_points else "pct",
            }
            for key, unit, in_points in INDICATORS
        ],
        "rotas_mais_lentas": latency_by_route(docs)[:3],
        "tools_com_mais_erro": failing_tools[:3],
        "consumo": {
            "tokens_entrada": tokens["total_entrada"],
            "tokens_saida": tokens["total_saida"],
            "pico_diario": tokens["pico"],
            "limite_diario": tokens["limite_diario"],
        },
        "leitura_nota": None,
        "juiz": judge(docs),
    }
