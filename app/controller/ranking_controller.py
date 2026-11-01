"""Endpoint de rankings de produtos.

GET /api/rankings/products
  - Sem parâmetros → ranking geral (todas as UFs).
  - ?state=SP       → ranking filtrado pelo estado SP.

Protegido pelo mesmo JWT Bearer usado no chat (X-API-Key + token do Auth service),
pois o ranking é exibido no frontend para o usuário logado, não no painel admin.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_user
from app.schemas.api import CurrentUser
from app.schemas.rankings import ProductRankingsResponse
from app.services import ranking_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rankings", tags=["rankings"])

User = Annotated[CurrentUser, Depends(get_current_user)]


@router.get(
    "/products",
    response_model=ProductRankingsResponse,
    summary="Top 5 produtos mais registrados e mais vencidos",
    description=(
        "Retorna dois rankings com os cinco produtos de maior destaque:\n\n"
        "- **registered**: mais consumidos/registrados no sistema.\n"
        "- **expired**: com mais ocorrências de vencimento.\n\n"
        "Sem `state` → ranking geral. Com `state=SP` → ranking do estado SP."
    ),
)
def get_product_rankings(
    user: User,
    state: str | None = Query(
        default=None,
        min_length=2,
        max_length=2,
        description="UF brasileira (ex: SP, RJ, MG). Ausente = ranking geral.",
    ),
) -> ProductRankingsResponse:
    # Valida e normaliza a UF
    try:
        validated_state = ranking_service.validate_state(state)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # Consulta o Redis via serviço
    try:
        return ranking_service.get_product_rankings(validated_state)
    except RuntimeError as exc:
        # Credenciais Redis não configuradas
        logger.error("[rankings] Configuração Redis ausente: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de rankings temporariamente indisponível. Verifique a configuração do Redis.",
        ) from exc
