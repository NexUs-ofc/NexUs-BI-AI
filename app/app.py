"""NexUs BI API (multi-agent).

Run from the project root:
    python -m uvicorn app.app:app --reload
Interactive docs: http://localhost:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import validate_config
from app.controller import chat_controller, metrics_controller

for problem in validate_config():
    print(f"[config] ATENÇÃO: {problem}")

app = FastAPI(
    title="NexUs BI AI",
    description="Assistente multiagente de BI: guardrails, roteador, FAQ, analista, recomendador, orquestrador e juiz.",
    version="0.1.0",
)

# CORS: lets the website (another address) call this API from the browser. Same policy as NexUs-Auth:
# any origin; the token in the Authorization header is what protects the data (no cookies are used).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_controller.router)
app.include_router(metrics_controller.router)


@app.get("/health", tags=["infra"])
def health() -> dict:
    problems = validate_config()
    return {"status": "ok" if not problems else "attention", "config_problems": problems}
