"""Schemas (Pydantic) trocados entre os agentes."""
from typing import Literal

from pydantic import BaseModel, Field

Rota = Literal["faq", "analista", "recomendador", "fora_escopo"]


class DecisaoRota(BaseModel):
    rota: Rota = Field(description="Agente que deve responder")
    motivo: str = Field(description="Justificativa curta da escolha")


class RespostaEspecialista(BaseModel):
    resposta: str
    contexto: str = Field(default="", description="Fonte da verdade usada (vai para o Juiz)")


class Veredito(BaseModel):
    aprovado: bool = Field(description="True se a resposta pode ser enviada ao usuário")
    nota: int = Field(description="Qualidade de 0 a 10")
    motivo: str = Field(description="Justificativa curta; se reprovado, o que corrigir")


class ResultadoGuardrail(BaseModel):
    permitido: bool
    motivo: str = ""
    texto: str = ""


class Resultado(BaseModel):
    resposta: str
    rota: str = ""
    passos: list[str] = Field(default_factory=list, description="Rastro para debug (--debug)")
