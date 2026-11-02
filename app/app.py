"""NexUs BI API: a única API do projeto (chatbot multiagente + dashboard + relatórios).

Run from the project root:
    python -m uvicorn app.app:app --reload
Interactive docs: http://localhost:8000/docs

As rotas de dashboard e relatórios (antes em report_generator/api.py, porta 8001) vêm de
app/controller/report_controller.py; o agendador de relatórios (report_generator/scheduler.py) é ligado
no lifespan abaixo.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import validate_config
from app.controller import admin_controller, chat_controller, ranking_controller, report_controller
from report_generator import scheduler
from report_generator.config import validate_config as validate_report_config

for problem in validate_config():
    print(f"[config] ATENÇÃO: {problem}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Liga o agendador de relatórios junto com a API (veja report_generator/scheduler.py)."""
    task = scheduler.start()
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="NexUs BI AI",
    description="Assistente multiagente de BI: guardrails, roteador, FAQ, analista, recomendador, orquestrador e juiz. "
    "Também serve o dashboard e os relatórios (JSON, gráficos e PDF).",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS: lets the website (another address) call this API from the browser. Same policy as NexUs-Auth:
# any origin; the token in the Authorization header is what protects the data (no cookies are used).
# Content-Disposition fica exposto para o site ler o nome do PDF baixado (GET /reports/{ano}/{mes}/pdf).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(chat_controller.router)
app.include_router(admin_controller.router)
app.include_router(report_controller.router)
app.include_router(ranking_controller.router)


@app.get("/health", tags=["infra"])
def health() -> dict:
    problems = validate_config() + [f"[relatórios] {p}" for p in validate_report_config()]
    return {"status": "ok" if not problems else "attention", "config_problems": problems}
