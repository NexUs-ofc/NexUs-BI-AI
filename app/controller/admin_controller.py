"""Admin panel endpoints. They only call the services.

Protected by the admin key (X-Admin-Key), the same in every NexUs service. The companies' API_KEY does not
open these routes.
"""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query

from app.auth.admin_key import verify_admin_key
from app.schemas.metrics import MetricsReport
from app.services import admin_service, langsmith_service, metrics_service

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_admin_key)])

Days = Query(7, ge=1, le=90, description="Período analisado (últimos N dias)")


@router.get("/session")
def session() -> dict:
    """Checks the key at the panel login: 200 with the right key, 401 without it."""
    return {"servico": "ceris-bi-ia", "autenticado": True, "verificado_em": datetime.now(UTC).isoformat(timespec="seconds")}


@router.get("/metrics")
def metrics(dias: int = Days) -> dict:
    """The BI IA page: summary, performance, cost and quality, from MongoDB. Fast: no LangSmith call."""
    return admin_service.build_dashboard(dias)


@router.get("/report")
def report(dias: int = Days) -> dict:
    """The period against the previous period of the same size, slowest routes and most failing tools."""
    return admin_service.build_period_report(dias)


@router.get("/langsmith")
def langsmith(dias: int = Days) -> dict:
    """Runs and errors per day, latency per chain and per agent, feedback. Slow: pages the LangSmith API."""
    return langsmith_service.build_langsmith(dias)


@router.get("/roi", response_model=MetricsReport)
def roi(
    days: int = Query(7, ge=1, le=365, description="Período analisado (últimos N dias)"),
    questions_per_user_week: int = Query(metrics_service.QUESTIONS_PER_USER_WEEK, ge=1, description="Perguntas por usuário por semana (cenários)"),
    minutes_saved_per_resolution: float = Query(metrics_service.MINUTES_SAVED_PER_RESOLUTION, ge=0, description="Minutos de analista economizados por pergunta resolvida (ROI)"),
    analyst_hour_brl: float = Query(metrics_service.ANALYST_HOUR_BRL, ge=0, description="Valor da hora do analista em R$ (ROI)"),
) -> MetricsReport:
    """Cost, scenarios for 100 and 1000 users and ROI in reais (it was GET /metrics/report)."""
    return metrics_service.build_report(days, questions_per_user_week, minutes_saved_per_resolution, analyst_hour_brl)
