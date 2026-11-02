"""Schemas do endpoint GET /api/rankings/products."""
from pydantic import BaseModel, ConfigDict, Field


def _to_camel(field: str) -> str:
    """Converte snake_case → camelCase (compatível com qualquer Pydantic v2)."""
    parts = field.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class RankedProduct(BaseModel):
    """Identificação, nome e pontuação do produto para o frontend."""

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    product_id: str = Field(description="Identificador do produto (member do ZSET)")
    product_name: str = Field(description="Nome do alimento no catálogo PostgreSQL")
    score: float = Field(description="Score do produto no ranking (quantidade de registros ou vencimentos)")


class ProductRankingsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    registered: list[RankedProduct] = Field(
        description="Top 5 produtos mais registrados, em ordem decrescente de score"
    )
    expired: list[RankedProduct] = Field(
        description="Top 5 produtos mais vencidos, em ordem decrescente de score"
    )
    state: str | None = Field(
        default=None,
        description="UF consultada (ex: 'SP'). None quando o ranking é geral (sem filtro estadual)",
    )
