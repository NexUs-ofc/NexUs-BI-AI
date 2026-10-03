"""Contratos da API (o que entra e o que sai dos endpoints)."""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    pergunta: str = Field(..., min_length=1, max_length=2000, examples=["Qual região vendeu mais?"])
    session_id: str | None = Field(
        default=None,
        description="Identifica a conversa. Se vier vazio, a API cria um e devolve na resposta.",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    debug: bool = Field(default=False, description="Se true, devolve os passos internos (rota, juiz, guardrails).")


class ChatResponse(BaseModel):
    session_id: str
    resposta: str
    rota: str = Field(..., examples=["analista"])
    passos: list[str] | None = None


class SessaoEncerradaResponse(BaseModel):
    session_id: str
    encerrada: bool
