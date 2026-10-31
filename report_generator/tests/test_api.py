import base64
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from report_generator import api, scheduler
from report_generator.auth import jwt_handler
from report_generator.config import BRAZIL_TZ

SECRET = base64.b64encode(b"x" * 32).decode()


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr("report_generator.auth.api_key.API_KEY", "chave")
    monkeypatch.setattr(jwt_handler, "JWT_SECRET", SECRET)
    # PDF falso: o fluxo da API não depende de navegador (o PDF real é testado em test_pdf.py)
    monkeypatch.setattr("report_generator.pipeline.render_pdf", lambda report: b"%PDF-teste")
    # "Hoje" fixo: a listagem mostra os últimos N meses a partir daqui
    monkeypatch.setattr(scheduler, "previous_month_now", lambda: (2026, 10))
    api._dashboard_cache.clear()
    return TestClient(api.app)


def _headers(kind: str) -> dict:
    return {"X-API-Key": "chave", "Authorization": f"Bearer {jwt_handler.create_test_token('1', profile_type=kind)}"}


def test_auth_required(client):
    assert client.get("/reports").status_code == 401
    assert client.get("/reports", headers={"X-API-Key": "chave"}).status_code == 401
    assert client.get("/dashboard").status_code == 401


def test_generate_publish_flow(client):
    admin, company = _headers("ADMIN"), _headers("COMPANY")
    assert client.post("/reports/2026/10/generate?sem_ia=true", headers=company).status_code == 403

    r = client.post("/reports/2026/10/generate?sem_ia=true", headers=admin)
    assert r.status_code == 202  # TestClient roda a tarefa em segundo plano antes de devolver
    assert client.get("/reports/2026/10/status", headers=admin).json()["status"] == "concluido"

    # rascunho: só o admin vê
    assert client.get("/reports/2026/10", headers=company).status_code == 404
    assert client.get("/reports/2026/10", headers=admin).json()["status"] == "rascunho"
    assert client.get("/reports", headers=company).json() == {"total": 0, "meses": []}

    assert client.post("/reports/2026/10/publish", headers=admin).status_code == 200
    pdf = client.get("/reports/2026/10/pdf", headers=company)
    assert pdf.status_code == 200 and pdf.content == b"%PDF-teste"
    assert pdf.headers["content-disposition"].startswith("inline")
    download = client.get("/reports/2026/10/pdf?download=true", headers=company)
    assert download.headers["content-disposition"].startswith("attachment")


def test_reports_grouped_by_month(client, db, monkeypatch):
    monkeypatch.setattr("report_generator.reports_listing.datetime",
                        type("FixedNow", (datetime,), {"now": classmethod(lambda cls, tz=None: datetime(
                            2026, 11, 2, tzinfo=BRAZIL_TZ))}))
    admin = _headers("ADMIN")
    for mes in (8, 9, 10):
        client.post(f"/reports/2026/{mes}/generate?sem_ia=true", headers=admin)
        client.post(f"/reports/2026/{mes}/publish", headers=admin)

    body = client.get("/reports", headers=_headers("COMPANY")).json()
    assert body["total"] == 3
    assert [m["titulo"] for m in body["meses"]] == ["Outubro 2026", "Setembro 2026", "Agosto 2026"]
    item = body["meses"][1]["relatorios"][0]
    assert item["data"] == "2026-09-30" and item["pdf"] == "/reports/2026/9/pdf"
    assert item["download"] == "/reports/2026/9/pdf?download=true"

    assert client.get("/reports?meses=2", headers=admin).json()["total"] == 2  # setembro e outubro
    assert client.get("/reports?busca=setembro", headers=admin).json()["meses"][0]["mes"] == 9


def test_dashboard(client):
    company = _headers("COMPANY")
    body = client.get("/dashboard", headers=company).json()
    assert body["meta"] == {"ano": 2026, "mes": 10, "fonte": "mock", "unidade": "itens",
                            "dataReferencia": "2026-10-31"}
    assert body["summary"]["wasteRate"] > 0 and body["monthlyTarget"] == 15.0
    assert client.get("/dashboard?ano=2026&mes=9", headers=company).json()["meta"]["mes"] == 9
    assert client.get("/dashboard?ano=2026", headers=company).status_code == 422


def test_dashboard_reports_source_failure(client, monkeypatch):
    def broken(ano, mes):
        raise RuntimeError("warehouse fora do ar")

    monkeypatch.setattr(api, "load_dashboard", lambda ano, mes, history: broken(ano, mes))
    r = client.get("/dashboard?ano=2026&mes=8", headers=_headers("COMPANY"))
    assert r.status_code == 503  # sem nenhuma busca boa anterior pra esse mês, não tem o que mostrar


def test_dashboard_cache_refresh_and_fallback(client, monkeypatch):
    """Mesmo período (slot) não busca de novo; se a busca de um período novo falhar, mantém o cache antigo."""
    company = _headers("COMPANY")
    body = client.get("/dashboard?ano=2026&mes=8", headers=company).json()

    def broken(ano, mes, history):
        raise RuntimeError("warehouse fora do ar ou cota estourada")

    monkeypatch.setattr(api, "load_dashboard", broken)
    same_slot = client.get("/dashboard?ano=2026&mes=8", headers=company)
    assert same_slot.status_code == 200 and same_slot.json() == body  # nem tentou buscar: slot não mudou

    api._dashboard_cache[(2026, 8)] = ("periodo-antigo", body)  # simula o relógio ter passado de período
    r = client.get("/dashboard?ano=2026&mes=8", headers=company)
    assert r.status_code == 200 and r.json() == body  # busca falhou, mas devolve os últimos dados bons


def test_cache_slot_refreshes_only_at_configured_hours():
    before = datetime(2026, 10, 31, 6, 30, tzinfo=BRAZIL_TZ)
    assert api._cache_slot(before) == "2026-10-30-20"  # antes das 8h: ainda o período da noite anterior
    after = datetime(2026, 10, 31, 8, 1, tzinfo=BRAZIL_TZ)
    assert api._cache_slot(after) == "2026-10-31-08"  # logo depois das 8h: já é o período novo
    evening = datetime(2026, 10, 31, 20, 30, tzinfo=BRAZIL_TZ)
    assert api._cache_slot(evening) == "2026-10-31-20"


def test_removed_endpoints_are_gone(client):
    admin = _headers("ADMIN")
    assert client.get("/reports/2026/10/html", headers=admin).status_code == 404
    assert client.get("/reports/2026/10/pdf-url", headers=admin).status_code == 404
    assert client.post("/reports/generate-previous", headers=admin).status_code in (404, 405)


def test_charts_and_pdf_url(client, monkeypatch):
    admin, company = _headers("ADMIN"), _headers("COMPANY")
    client.post("/reports/2026/10/generate?sem_ia=true", headers=admin)
    client.post("/reports/2026/10/publish", headers=admin)

    charts = client.get("/reports/2026/10/charts", headers=company).json()
    assert {"periodo", "disponivel", "resumo", "kpis", "evolucao", "categorias", "regioes", "momentoDescarte",
            "despensa", "acoesApp"} <= set(charts)
    assert charts["periodo"]["ano"] == 2026

    # sem Supabase (dev): aponta para a própria API
    url = client.get("/reports/2026/10/pdf-url", headers=company).json()
    assert url["origem"] == "api" and url["url"] == "/reports/2026/10/pdf"
    # com Supabase: URL assinada
    monkeypatch.setattr(api.files, "signed_url", lambda uri, seconds: "https://x.supabase.co/signed?token=1")
    url = client.get("/reports/2026/10/pdf-url", headers=company).json()
    assert url["origem"] == "supabase" and url["url"].startswith("https://x.supabase.co/signed")
