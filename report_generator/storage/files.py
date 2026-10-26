"""Armazenamento dos PDFs: Google Cloud Storage, ou pasta local quando GCS_BUCKET está vazio (dev).

GCS usa as credenciais padrão do Google (GOOGLE_APPLICATION_CREDENTIALS ou a conta do Cloud Run).
Caminho do arquivo: {GCS_PREFIX}/{ano}/{mes:02d}.pdf  (ex.: relatorios/2026/10.pdf)
"""
from functools import lru_cache
from pathlib import Path

from report_generator.config import GCS_BUCKET, GCS_PREFIX, OUTPUT_DIR


def _name(ano: int, mes: int) -> str:
    return f"{GCS_PREFIX}/{ano}/{mes:02d}.pdf"


@lru_cache(maxsize=1)
def _bucket():
    from google.cloud import storage

    return storage.Client().bucket(GCS_BUCKET)


def save_pdf(content: bytes, ano: int, mes: int) -> str:
    """Grava o PDF e devolve a URI (gs://... ou caminho local)."""
    name = _name(ano, mes)
    if GCS_BUCKET:
        _bucket().blob(name).upload_from_string(content, content_type="application/pdf")
        return f"gs://{GCS_BUCKET}/{name}"
    path = OUTPUT_DIR / f"{ano}-{mes:02d}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return str(path)


def load_pdf(uri: str) -> bytes:
    if uri.startswith("gs://"):
        name = uri.removeprefix(f"gs://{GCS_BUCKET}/")
        return _bucket().blob(name).download_as_bytes()
    return Path(uri).read_bytes()
