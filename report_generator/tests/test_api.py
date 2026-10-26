import base64

import pytest
from fastapi.testclient import TestClient

from report_generator import api
from report_generator.auth import jwt_handler

SECRET = base64.b64encode(b"x" * 32).decode()


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr("report_generator.auth.api_key.API_KEY", "chave")
    monkeypatch.setattr(jwt_handler, "JWT_SECRET", SECRET)
    return TestClient(api.app)


def _headers(kind: str) -> dict:
    return {"X-API-Key": "chave", "Authorization": f"Bearer {jwt_handler.create_test_token('1', profile_type=kind)}"}


def test_auth_required(client):
    assert client.get("/reports").status_code == 401
    assert client.get("/reports", headers={"X-API-Key": "chave"}).status_code == 401


def test_generate_publish_flow(client):
    admin, company = _headers("ADMIN"), _headers("COMPANY")
    assert client.post("/reports/2026/10/generate?sem_ia=true", headers=company).status_code == 403

    r = client.post("/reports/2026/10/generate?sem_ia=true", headers=admin)
    assert r.status_code == 202  # TestClient roda a tarefa em segundo plano antes de devolver
    assert client.get("/reports/2026/10/status", headers=admin).json()["status"] == "concluido"

    # rascunho: só o admin vê
    assert client.get("/reports/2026/10", headers=company).status_code == 404
    assert client.get("/reports/2026/10", headers=admin).json()["status"] == "rascunho"

    assert client.post("/reports/2026/10/publish", headers=admin).status_code == 200
    assert client.get("/reports", headers=company).json()[0]["mes"] == 10
    assert "Outubro de 2026" in client.get("/reports/2026/10/html", headers=company).text
    pdf = client.get("/reports/2026/10/pdf", headers=company)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
