import httpx
import pytest

from report_generator.storage import files


@pytest.fixture
def supabase(monkeypatch):
    """Simula a API do Supabase Storage num dicionário em memória."""
    bucket: dict[str, bytes] = {}
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        name = request.url.path.removeprefix("/storage/v1/object/")
        if request.method == "POST":
            bucket[name] = request.content
            return httpx.Response(200, json={"Key": name})
        if name in bucket:
            return httpx.Response(200, content=bucket[name])
        return httpx.Response(404, json={"error": "not_found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(files.httpx, "post", client.post)
    monkeypatch.setattr(files.httpx, "get", client.get)
    monkeypatch.setattr(files, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(files, "SUPABASE_KEY", "service-key")
    monkeypatch.setattr(files, "SUPABASE_BUCKET", "reports")
    monkeypatch.setattr(files, "SUPABASE_PREFIX", "relatorios")
    return bucket, calls


def test_save_and_load_pdf_on_supabase(supabase):
    bucket, calls = supabase
    uri = files.save_pdf(b"%PDF-teste", 2026, 10)

    assert uri == "supabase://reports/relatorios/2026/10.pdf"
    assert bucket["reports/relatorios/2026/10.pdf"] == b"%PDF-teste"
    upload = calls[0]
    assert upload.headers["authorization"] == "Bearer service-key"
    assert upload.headers["x-upsert"] == "true"
    assert upload.headers["content-type"] == "application/pdf"

    assert files.load_pdf(uri) == b"%PDF-teste"


def test_supabase_error_is_reported(supabase):
    with pytest.raises(RuntimeError, match="404"):
        files.load_pdf("supabase://reports/relatorios/2020/01.pdf")


def test_local_folder_when_supabase_is_not_configured(monkeypatch, tmp_path):
    monkeypatch.setattr(files, "SUPABASE_URL", "")
    monkeypatch.setattr(files, "OUTPUT_DIR", tmp_path)
    uri = files.save_pdf(b"%PDF-local", 2026, 9)
    assert uri == str(tmp_path / "2026-09.pdf")
    assert files.load_pdf(uri) == b"%PDF-local"
