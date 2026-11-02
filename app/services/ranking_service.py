"""Serviço de rankings de produtos.

Consulta as pontuações no Redis e resolve os nomes no catálogo PostgreSQL.
"""
import re

from app.repository import food_repository, ranking_repository
from app.schemas.rankings import ProductRankingsResponse, RankedProduct

_FOOD_ID = re.compile(r"[1-9][0-9]{0,9}")

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


def _food_id(member: str) -> int | None:
    if not _FOOD_ID.fullmatch(member):
        return None
    food_id = int(member)
    return food_id if food_id <= 2_147_483_647 else None


def _to_ranked_products(pairs: list[tuple[str, float]], food_names: dict[int, str]) -> list[RankedProduct]:
    products = []
    for member, score in pairs:
        food_id = _food_id(member)
        name = food_names.get(food_id) if food_id is not None else None
        if name:
            products.append(RankedProduct(product_id=member, product_name=name, score=score))
    return products


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
        food_ids = {
            food_id
            for member, _ in registered_raw + expired_raw
            if (food_id := _food_id(member)) is not None
        }
        food_names = food_repository.find_food_names(sorted(food_ids))
    except Exception as error:
        raise RuntimeError("Não foi possível consultar os rankings de produtos.") from error

    return ProductRankingsResponse(
        registered=_to_ranked_products(registered_raw, food_names),
        expired=_to_ranked_products(expired_raw, food_names),
        state=state,
    )
