"""NexUs BI API (multi-agent) — API unificada.

Incorpora todos os endpoints do chatbot e do gerador de relatórios numa única aplicação FastAPI.

Run from the project root:
    python -m uvicorn app.app:app --reload
Interactive docs: http://localhost:8000/docs
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import validate_config
from app.controller import admin_controller, chat_controller, ranking_controller
from app.controller import report_controller
from report_generator import scheduler as report_scheduler

for problem in validate_config():
    print(f"[config] ATENÇÃO: {problem}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Liga o agendador mensal do gerador de relatórios junto com a API."""
    task = report_scheduler.start()
    yield
    if task:
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=2)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass


app = FastAPI(
    title="NexUs BI AI",
    description=(
        "Assistente multiagente de BI: guardrails, roteador, FAQ, analista, recomendador, "
        "orquestrador e juiz. Inclui dashboard, relatórios e geração de PDFs."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# CORS: lets the website (another address) call this API from the browser. Same policy as NexUs-Auth:
# any origin; the token in the Authorization header is what protects the data (no cookies are used).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# --- Chatbot & admin routes ---
app.include_router(chat_controller.router)
app.include_router(admin_controller.router)
app.include_router(ranking_controller.router)

# --- Report generator routes (formerly report_generator/api.py) ---
app.include_router(report_controller.router)


@app.get("/health", tags=["infra"])
def health() -> dict:
    from report_generator.config import validate_config as rg_validate
    chatbot_problems = validate_config()
    report_problems = rg_validate()
    all_problems = chatbot_problems + report_problems
    return {
        "status": "ok" if not all_problems else "attention",
        "config_problems": all_problems,
    }
