"""Proteção das rotas: o cliente precisa mandar a chave da API no header X-API-Key."""
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import API_KEY

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _limpar(valor: str) -> str:
    """Tira espaços e aspas das pontas (erro comum ao copiar a chave do .env)."""
    return valor.strip().strip('"').strip("'").strip()


def verificar_api_key(chave: str | None = Security(_header)) -> None:
    esperada = _limpar(API_KEY)
    if not esperada:
        # Falha fechada: sem chave configurada, ninguém usa a API.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "API_KEY não configurada no servidor.")
    if not chave:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Header X-API-Key ausente. No /docs, clique em 'Authorize' e informe a chave.",
        )
    if not secrets.compare_digest(_limpar(chave).encode(), esperada.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chave de API inválida (diferente da API_KEY do .env).")
