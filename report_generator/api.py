"""API do gerador de relatórios, consumida pelo site (NexUs-Web).

    python -m uvicorn report_generator.api:app --reload --port 8001   ->  http://localhost:8001/docs

Leitura (COMPANY e ADMIN; todo relatório gerado já é publicado):
    GET  /dashboard                     dados das visualizações do Dashboard (Gold do Databricks ou mock)
    GET  /reports                       PDFs agrupados por mês (tela Relatórios)
    GET  /reports/{ano}/{mes}           JSON completo do relatório
    GET  /reports/{ano}/{mes}/charts    séries prontas para gráficos (evolução, categorias, regiões, momento, UF)
    GET  /reports/{ano}/{mes}/pdf       o PDF (?download=true para baixar em vez de abrir)
    GET  /reports/{ano}/{mes}/pdf-url   URL temporária (assinada) do PDF no Supabase Storage, para o site abrir direto
Escrita (ADMIN):
    POST /reports/{ano}/{mes}/generate  gera em segundo plano (202); acompanhe em .../status
    GET  /reports/{ano}/{mes}/status

A geração automática do mês anterior roda dentro da API (scheduler.py).
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Path,
    Query,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from report_generator import scheduler
from report_generator.auth.dependencies import (
    CurrentUser,
    require_reader,
    require_writer,
)
from report_generator.charts_data import charts_payload
from report_generator.config import (
    BRAZIL_TZ,
    DASHBOARD_REFRESH_HOURS,
    HISTORY_MONTHS,
    SIGNED_URL_SECONDS,
    WRITE_PROFILES,
    validate_config,
)
from report_generator.data.loader import load_dashboard
from report_generator.reports_listing import group_by_month, merge_bucket
from report_generator.storage import files, mongo

log = logging.getLogger("report_generator")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Liga o agendador mensal junto com a API (veja scheduler.py)."""
    task = scheduler.start()
    yield
    if task:
        task.cancel()


app = FastAPI(title="NexUs BI · Gerador de relatórios", version="0.3.0", lifespan=lifespan)
# Mesmo critério do chatbot (app/app.py): o site roda em outro endereço; quem protege é o token Bearer
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])

Ano = Annotated[int, Path(ge=2020, le=2100)]
Mes = Annotated[int, Path(ge=1, le=12)]
Reader = Annotated[CurrentUser, Depends(require_reader)]
Writer = Annotated[CurrentUser, Depends(require_writer)]

# (ano, mes) -> (rótulo do período de cache, dados). Veja `_cache_slot`.
_dashboard_cache: dict[tuple[int, int], tuple[str, dict]] = {}


def _cache_slot(now: datetime) -> str:
    """Rótulo do período de cache atual, que só muda nos horários de DASHBOARD_REFRESH_HOURS (Brasília) —
    a busca sempre pega a Gold do dia já depois do Job_NexUs_BI das 7h, nunca dados de ontem por sorte do
    horário em que a primeira pessoa acessou o site."""
    local = now.astimezone(BRAZIL_TZ)
    passados = [h for h in DASHBOARD_REFRESH_HOURS if h <= local.hour]
    if passados:
        return f"{local:%Y-%m-%d}-{max(passados):02d}"
    ontem = local - timedelta(days=1)
    return f"{ontem:%Y-%m-%d}-{max(DASHBOARD_REFRESH_HOURS):02d}"


def _is_admin(user: CurrentUser) -> bool:
    return user.profile_type in WRITE_PROFILES


def _get_visible(ano: int, mes: int, user: CurrentUser) -> dict:
    report = mongo.find_report(ano, mes)
    if not report:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Relatório de {mes:02d}/{ano} não encontrado.")
    return report


def _history(ano: int, mes: int) -> list[dict]:
    """Meses anteriores do Mongo para a linha do Dashboard no mock (na Gold a série vem do Databricks).
    Sem Mongo, o Dashboard sai só com o mês atual."""
    try:
        return mongo.find_previous_dados(ano, mes, max(HISTORY_MONTHS, 11))
    except Exception:
        log.warning("Dashboard sem histórico: MongoDB indisponível", exc_info=True)
        return []


@app.get("/health")
def health() -> dict:
    problems = validate_config()
    return {"status": "ok" if not problems else "incompleto", "problemas": problems}


@app.get("/dashboard")
def dashboard(
    _user: Reader,
    ano: Annotated[int | None, Query(ge=2020, le=2100, description="padrão: o mês atual (parcial)")] = None,
    mes: Annotated[int | None, Query(ge=1, le=12)] = None,
) -> dict:
    """Dados de todas as visualizações do Dashboard, no formato `DashboardData` do site."""
    if (ano is None) != (mes is None):
        raise HTTPException(422, "Informe ano e mes juntos (ou nenhum dos dois).")
    if ano is None:
        # Mês ATUAL (parcial): o anterior pode não ter foto da despensa e a tela ficaria zerada.
        ano, mes = scheduler.current_month()
    slot = _cache_slot(datetime.now(BRAZIL_TZ))
    cached = _dashboard_cache.get((ano, mes))
    if cached and cached[0] == slot:
        return cached[1]
    try:
        data = load_dashboard(ano, mes, lambda: _history(ano, mes))
    except Exception as error:
        if cached:
            # Databricks fora do ar ou cota estourada: mantém os últimos dados bons em vez de quebrar o
            # site. O JSON já carrega sua própria `meta.dataReferencia`, então o front mostra de quando é.
            log.warning("Falha ao atualizar o dashboard de %02d/%d; mantendo os dados de %s (%s)", mes, ano,
                       cached[0], error)
            return cached[1]
        log.exception("Falha ao montar o dashboard de %02d/%d", mes, ano)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Não foi possível carregar os dados do dashboard agora.") from error
    _dashboard_cache[(ano, mes)] = (slot, data)
    return data


@app.get("/reports")
def list_reports(
    user: Reader,
    ano: Annotated[int | None, Query(ge=2000, le=2100, description="filtra pelo ano")] = None,
    mes: Annotated[int | None, Query(ge=1, le=12, description="filtra pelo mês (1 a 12)")] = None,
    busca: Annotated[str | None, Query(max_length=100, description="filtra pelo nome")] = None,
    meses: Annotated[int | None, Query(ge=1, le=600, description="obsoleto: ignorado, a lista traz todos")] = None,
) -> dict:
    """TODOS os relatórios com PDF, agrupados por mês (do mais recente para o mais antigo).
    Filtros: `ano`, `mes` e `busca` (nome). `meses` é aceito só por compatibilidade e não limita nada."""
    avisos = []
    try:
        reports = mongo.list_reports()
    except Exception as error:
        log.warning("Listagem de relatórios sem Mongo: usando só o bucket", exc_info=True)
        reports, avisos = [], [*avisos, f"Mongo indisponível: {type(error).__name__}"]
    try:
        reports = merge_bucket(reports, files.list_pdfs())
    except Exception as error:
        log.exception("Não foi possível listar o bucket de PDFs")
        avisos.append(f"Bucket de PDFs indisponível: {error}"[:300])
    result = group_by_month(reports, ano=ano, mes=mes, busca=busca)
    return {**result, "avisos": avisos} if avisos else result


@app.post("/reports/{ano}/{mes}/generate", status_code=status.HTTP_202_ACCEPTED)
def generate(ano: Ano, mes: Mes, background: BackgroundTasks, _user: Writer,
             sem_ia: Annotated[bool, Query(description="narrativa por regras, sem Gemini")] = False) -> dict:
    if scheduler.is_running(ano, mes):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma geração em andamento para este mês.")
    mongo.set_job(ano, mes, "na_fila")
    background.add_task(scheduler.run_job, ano, mes, use_ai=not sem_ia)
    return {"ano": ano, "mes": mes, "status": "na_fila", "acompanhe": f"/reports/{ano}/{mes}/status"}


@app.get("/reports/{ano}/{mes}/status")
def job_status(ano: Ano, mes: Mes, _user: Writer) -> dict:
    job = mongo.find_job(ano, mes)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nenhuma geração registrada para este mês.")
    return job


@app.get("/reports/{ano}/{mes}")
def get_report(ano: Ano, mes: Mes, user: Reader) -> dict:
    return _get_visible(ano, mes, user)


@app.get("/reports/{ano}/{mes}/charts")
def get_report_charts(ano: Ano, mes: Mes, user: Reader) -> dict:
    """Séries prontas para o site desenhar gráficos (lidas do Mongo: não consome o Databricks)."""
    return charts_payload(_get_visible(ano, mes, user))


def _pdf_uri(ano: int, mes: int, user: CurrentUser) -> str:
    """URI do PDF: a do Mongo e, se o relatório não está lá, a do próprio bucket (o PDF existe, então serve)."""
    try:
        report = _get_visible(ano, mes, user)
        if report.get("pdf"):
            return report["pdf"]["uri"]
    except HTTPException:
        pass
    try:
        uri = files.list_pdfs().get((ano, mes))
    except Exception:
        log.warning("Falha ao consultar o bucket de PDFs", exc_info=True)
        uri = None
    if not uri:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este relatório ainda não tem PDF.")
    return uri


@app.get("/reports/{ano}/{mes}/pdf")
def get_report_pdf(ano: Ano, mes: Mes, user: Reader,
                   download: Annotated[bool, Query(description="true = baixar; false = abrir no navegador")] = False
                   ) -> Response:
    content = files.load_pdf(_pdf_uri(ano, mes, user))
    disposition = "attachment" if download else "inline"
    headers = {"Content-Disposition": f'{disposition}; filename="nexus-bi-{ano}-{mes:02d}.pdf"'}
    return Response(content, media_type="application/pdf", headers=headers)


@app.get("/reports/{ano}/{mes}/pdf-url")
def get_report_pdf_url(ano: Ano, mes: Mes, user: Reader) -> dict:
    """URL assinada e temporária do PDF no bucket privado do Supabase: o site abre (iframe, nova aba ou
    download) direto do Storage, sem a service role key e sem passar os bytes pela API. Sem Supabase
    configurado (desenvolvimento) devolve o caminho da própria API."""
    uri = _pdf_uri(ano, mes, user)
    try:
        url = files.signed_url(uri, SIGNED_URL_SECONDS)
    except RuntimeError as error:
        log.error("Falha ao assinar o PDF de %02d/%d: %s", mes, ano, error)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Não foi possível gerar o link do PDF agora.") from error
    return {"url": url or f"/reports/{ano}/{mes}/pdf", "expiraEmSegundos": SIGNED_URL_SECONDS if url else None,
            "origem": "supabase" if url else "api"}



