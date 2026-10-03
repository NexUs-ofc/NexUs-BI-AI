"""API do NexUs BI (multiagente).

Rodar na raiz do projeto:
    uvicorn app.app:app --reload
Documentação interativa: http://localhost:8000/docs
"""
from fastapi import FastAPI

from app.config import validar_config
from app.controller import chat_controller

for problema in validar_config():
    print(f"[config] ATENÇÃO: {problema}")

app = FastAPI(
    title="NexUs BI AI",
    description="Assistente multiagente de BI: guardrails, roteador, FAQ, analista, recomendador, orquestrador e juiz.",
    version="0.1.0",
)

app.include_router(chat_controller.router)


@app.get("/health", tags=["infra"])
def health() -> dict:
    problemas = validar_config()
    return {"status": "ok" if not problemas else "atencao", "problemas_de_configuracao": problemas}
