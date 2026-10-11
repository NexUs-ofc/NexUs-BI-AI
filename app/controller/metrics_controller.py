"""Metrics endpoint for the team (cost, latency, errors, ROI). It only calls the service.

Protected by the X-API-Key only: it is an internal report, not used by the companies.
"""
from fastapi import APIRouter, Depends, Query

from app.auth.api_key import verify_api_key
from app.schemas.metrics import MetricsReport
from app.services import metrics_service

router = APIRouter(prefix="/metrics", tags=["metrics"], dependencies=[Depends(verify_api_key)])


@router.get("/report", response_model=MetricsReport)
def report(
    days: int = Query(7, ge=1, le=365, description="Período analisado (últimos N dias)"),
    questions_per_user_week: int = Query(metrics_service.QUESTIONS_PER_USER_WEEK, ge=1, description="Perguntas por usuário por semana (cenários)"),
    minutes_saved_per_resolution: float = Query(metrics_service.MINUTES_SAVED_PER_RESOLUTION, ge=0, description="Minutos de analista economizados por pergunta resolvida (ROI)"),
    analyst_hour_brl: float = Query(metrics_service.ANALYST_HOUR_BRL, ge=0, description="Valor da hora do analista em R$ (ROI)"),
) -> MetricsReport:
    return metrics_service.build_report(days, questions_per_user_week, minutes_saved_per_resolution, analyst_hour_brl)
