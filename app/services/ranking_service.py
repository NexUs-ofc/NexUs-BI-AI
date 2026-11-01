"""Serviço de rankings de produtos.

Orquestra as chamadas ao repositório Redis e monta a resposta no formato
esperado pelo controller, tratando erros de conexão e listas vazias com segurança.
"""
import logging

from app.repository import ranking_repository
from app.schemas.rankings import ProductRankingsResponse, RankedProduct

logger = logging.getLogger(__name__)

# UFs brasileiras válidas (26 estados + DF)
_VALID_STATES: frozenset[str] = frozenset({
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
})


def validate_state(state: str | None) -> str | None:
    """Normaliza e valida a UF.

    Returns:
        UF em maiúsculas, ou ``None`` se ausente.

    Raises:
        ValueError: se o estado não for uma UF brasileira válida.
    """
    if state is None:
        return None
    normalized = state.strip().upper()
    if normalized not in _VALID_STATES:
        raise ValueError(
            f"Estado inválido: '{state}'. Informe uma UF brasileira válida "
            f"(ex: SP, RJ, MG)."
        )
    return normalized


def _to_ranked_products(pairs: list[tuple[str, float]]) -> list[RankedProduct]:
    return [RankedProduct(product_id=member, score=score) for member, score in pairs]


def get_product_rankings(state: str | None) -> ProductRankingsResponse:
    """Busca os dois rankings (registrados e vencidos) no Redis e os retorna formatados.

    Args:
        state: UF já validada pelo controller (ou ``None`` para ranking geral).

    Returns:
        :class:`ProductRankingsResponse` pronto para serialização.
    """
    try:
        registered_raw = ranking_repository.get_registered_ranking(state)
        expired_raw = ranking_repository.get_expired_ranking(state)
    except RuntimeError as exc:
        # Credenciais Redis ausentes: propaga para o controller logar e retornar 503
        raise
    except Exception as exc:
        logger.error("[rankings] Falha ao consultar o Redis: %s", exc, exc_info=True)
        # Retorna listas vazias em vez de derrubar a rota por falha do cache
        registered_raw = []
        expired_raw = []

    return ProductRankingsResponse(
        registered=_to_ranked_products(registered_raw),
        expired=_to_ranked_products(expired_raw),
        state=state,
    )
