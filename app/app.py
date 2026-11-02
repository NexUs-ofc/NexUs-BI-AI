"""NexUs BI API: a única API do projeto (chatbot multiagente + dashboard + relatórios).

Run from the project root:
    python -m uvicorn app.app:app --reload
Interactive docs: http://localhost:8000/docs

As rotas de dashboard e relatórios (antes em report_generator/api.py, porta 8001) vêm de
app/controller/report_controller.py; o agendador de relatórios (report_generator/scheduler.py) é ligado
no lifespan abaixo.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    CHAT_TIMEOUT_S,
    LLM_MAX_RETRIES,
    LLM_MODEL,
    LLM_THINKING_LEVEL,
    LLM_TIMEOUT_S,
    MONGODB_DB,
    QDRANT_COLLECTION_FAQ,
    validate_config,
)
from app.controller import (
    admin_controller,
    chat_controller,
    ranking_controller,
    report_controller,
)
from app.model.llm import uses_interactions_api
from app.observability import trace
from report_generator import scheduler
from report_generator.config import DATA_SOURCE
from report_generator.config import validate_config as validate_report_config

trace.configure_logging()

for problem in validate_config():
    trace.log("config.ATENCAO", 30, problema=problem)
if DATA_SOURCE == "mock":
    trace.log("config.ATENCAO", 30, problema="REPORT_DATA_SOURCE=mock: dashboard e relatórios com dados FICTÍCIOS")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Liga o agendador de relatórios junto com a API (veja report_generator/scheduler.py)."""
    trace.log(
        "api.inicio",
        modelo=LLM_MODEL,
        api_gemini="interactions" if uses_interactions_api(LLM_MODEL) else "generateContent",
        raciocinio=LLM_THINKING_LEVEL if uses_interactions_api(LLM_MODEL) else None,
        timeout_chamada_s=LLM_TIMEOUT_S,
        retries_sdk=LLM_MAX_RETRIES,
        timeout_chat_s=CHAT_TIMEOUT_S,
        mongodb_db=MONGODB_DB,
        qdrant_collection=QDRANT_COLLECTION_FAQ,
        relatorios_fonte=DATA_SOURCE,
    )
    task = scheduler.start()
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="NexUs BI AI",
    description="Assistente de BI: guardrails, um agente com FAQ (Qdrant) e relatórios (MongoDB), conferência de números. "
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
    expose_headers=["Content-Disposition", "X-Request-Id"],
)

# Logs por requisição nas rotas do chat (observability/trace.py): início, fim, status e o tempo de cada
# serviço externo. As outras rotas seguem só com o log de acesso do uvicorn.
_TRACED_PREFIXES = ("/chat",)


@app.middleware("http")
async def trace_chat_requests(request: Request, call_next):
    if not request.url.path.startswith(_TRACED_PREFIXES):
        return await call_next(request)
    request_trace = trace.start_request()
    trace.log("requisicao.inicio", metodo=request.method, rota=request.url.path)
    try:
        response = await call_next(request)
    except Exception as error:
        trace.log("requisicao.ERRO", 40, erro=type(error).__name__, detalhe=trace.redact(error),
                  **request_trace.summary())
        raise
    trace.log("requisicao.fim", status=response.status_code, **request_trace.summary())
    response.headers["X-Request-Id"] = request_trace.request_id
    return response


app.include_router(chat_controller.router)
app.include_router(admin_controller.router)
app.include_router(report_controller.router)
app.include_router(ranking_controller.router)


@app.get("/health", tags=["infra"])
def health() -> dict:
    problems = validate_config() + [f"[relatórios] {p}" for p in validate_report_config()]
    if DATA_SOURCE == "mock":
        problems.append("[relatórios] REPORT_DATA_SOURCE=mock: dashboard e relatórios usam dados FICTÍCIOS")
    return {"status": "ok" if not problems else "attention", "config_problems": problems}
