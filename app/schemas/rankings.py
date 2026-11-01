"""Schemas do endpoint GET /api/rankings/products."""
from pydantic import BaseModel, Field


class RankedProduct(BaseModel):
    product_id: str = Field(description="Identificador do produto (member do ZSET)")
    score: float = Field(description="Score do produto no ranking (quantidade de registros ou vencimentos)")


class ProductRankingsResponse(BaseModel):
    registered: list[RankedProduct] = Field(
        description="Top 5 produtos mais registrados/consumidos, em ordem decrescente de score"
    )
    expired: list[RankedProduct] = Field(
        description="Top 5 produtos mais vencidos, em ordem decrescente de score"
    )
    state: str | None = Field(
        default=None,
        description="UF consultada (ex: 'SP'). None quando o ranking é geral (sem filtro estadual)",
    )
