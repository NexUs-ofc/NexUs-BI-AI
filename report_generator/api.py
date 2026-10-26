"""API do gerador de relatórios, consumida pela interface web.

    python -m uvicorn report_generator.api:app --reload --port 8001   ->  http://localhost:8001/docs

A geração leva alguns minutos (3 agentes + PDF), então POST .../generate responde na hora (202) e roda em
segundo plano; a web acompanha por GET .../status.

Empresas (COMPANY) só enxergam relatórios publicados; ADMIN vê também os rascunhos.
"""
import logging
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
from fastapi.responses import HTMLResponse, Response

from report_generator import pipeline
from report_generator.auth.dependencies import (
    CurrentUser,
    require_reader,
    require_writer,
)
from report_generator.config import WRITE_PROFILES, validate_config
from report_generator.rendering.html import render_html
from report_generator.storage import files, mongo

log = logging.getLogger("report_generator")
app = FastAPI(title="NexUs BI · Gerador de relatórios", version="0.1.0")

Ano = Annotated[int, Path(ge=2020, le=2100)]
Mes = Annotated[int, Path(ge=1, le=12)]
Reader = Annotated[CurrentUser, Depends(require_reader)]
Writer = Annotated[CurrentUser, Depends(require_writer)]


def _get_visible(ano: int, mes: int, user: CurrentUser) -> dict:
    report = mongo.find_report(ano, mes)
    if not report or (report.get("status") != "publicado" and user.profile_type not in WRITE_PROFILES):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Relatório de {mes:02d}/{ano} não encontrado.")
    return report


def _generate_job(ano: int, mes: int, use_ai: bool) -> None:
    mongo.set_job(ano, mes, "em_execucao")
    try:
        pipeline.run(ano, mes, use_ai=use_ai)
        mongo.set_job(ano, mes, "concluido")
    except Exception as error:
        log.exception("Falha ao gerar %02d/%d", mes, ano)
        mongo.set_job(ano, mes, "erro", erro=f"{type(error).__name__}: {str(error)[:500]}")


@app.get("/health")
def health() -> dict:
    problems = validate_config()
    return {"status": "ok" if not problems else "incompleto", "problemas": problems}


@app.get("/reports")
def list_reports(user: Reader) -> list[dict]:
    reports = mongo.list_reports()
    if user.profile_type not in WRITE_PROFILES:
        reports = [r for r in reports if r.get("status") == "publicado"]
    return reports


@app.post("/reports/{ano}/{mes}/generate", status_code=status.HTTP_202_ACCEPTED)
def generate(ano: Ano, mes: Mes, background: BackgroundTasks, _user: Writer,
             sem_ia: Annotated[bool, Query(description="narrativa por regras, sem Gemini")] = False) -> dict:
    job = mongo.find_job(ano, mes)
    if job and job.get("status") == "em_execucao":
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma geração em andamento para este mês.")
    mongo.set_job(ano, mes, "na_fila")
    background.add_task(_generate_job, ano, mes, not sem_ia)
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


@app.get("/reports/{ano}/{mes}/html", response_class=HTMLResponse)
def get_report_html(ano: Ano, mes: Mes, user: Reader) -> str:
    return render_html(_get_visible(ano, mes, user))


@app.get("/reports/{ano}/{mes}/pdf")
def get_report_pdf(ano: Ano, mes: Mes, user: Reader) -> Response:
    report = _get_visible(ano, mes, user)
    if not report.get("pdf"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este relatório ainda não tem PDF.")
    content = files.load_pdf(report["pdf"]["uri"])
    headers = {"Content-Disposition": f'inline; filename="nexus-bi-{ano}-{mes:02d}.pdf"'}
    return Response(content, media_type="application/pdf", headers=headers)


@app.post("/reports/{ano}/{mes}/publish")
def publish(ano: Ano, mes: Mes, _user: Writer) -> dict:
    if not mongo.set_status(ano, mes, "publicado"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Relatório de {mes:02d}/{ano} não encontrado.")
    return {"ano": ano, "mes": mes, "status": "publicado"}
