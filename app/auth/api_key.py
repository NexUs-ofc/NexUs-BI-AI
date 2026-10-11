"""Route protection: the client must send the API key in the X-API-Key header."""
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import API_KEY

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _clean(value: str) -> str:
    """Strip spaces and quotes from the ends (common mistake when copying the key from .env)."""
    return value.strip().strip('"').strip("'").strip()


def verify_api_key(key: str | None = Security(_header)) -> None:
    expected = _clean(API_KEY)
    if not expected:
        # Fail closed: with no key configured, nobody can use the API.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "API_KEY não configurada no servidor.")
    if not key:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Header X-API-Key ausente. No /docs, clique em 'Authorize' e informe a chave.",
        )
    if not secrets.compare_digest(_clean(key).encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chave de API inválida (diferente da API_KEY do .env).")
