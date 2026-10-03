"""Pydantic schemas exchanged between the agents."""
from typing import Literal

from pydantic import BaseModel, Field

Route = Literal["faq", "analyst", "recommender", "out_of_scope"]


class RouteDecision(BaseModel):
    route: Route = Field(description="Agente que deve responder")
    reason: str = Field(description="Justificativa curta da escolha")


class SpecialistAnswer(BaseModel):
    answer: str
    context: str = Field(default="", description="Source of truth used by the specialist (sent to the judge)")


class Verdict(BaseModel):
    approved: bool = Field(description="True se a resposta pode ser enviada ao usuário")
    score: int = Field(description="Qualidade de 0 a 10")
    reason: str = Field(description="Justificativa curta; se reprovado, o que corrigir")


class GuardrailResult(BaseModel):
    allowed: bool
    reason: str = ""
    text: str = ""


class Result(BaseModel):
    answer: str
    route: str = ""
    steps: list[str] = Field(default_factory=list, description="Debug trace (debug=true)")
