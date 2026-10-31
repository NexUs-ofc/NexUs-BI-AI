"""Admin panel protection: the panel sends the admin key in the X-Admin-Key header.

The key is the same in every NexUs service (Auth, Core, Notify, IA and BI IA), so the panel logs in once.
It is separate from API_KEY: the companies' key never opens the panel, and the panel key never opens /chat.
"""
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.auth.api_key import _clean
from app.config import ADMIN_API_KEY

ADMIN_KEY_HEADER = "X-Admin-Key"

_header = APIKeyHeader(name=ADMIN_KEY_HEADER, auto_error=False)


def verify_admin_key(key: str | None = Security(_header)) -> None:
    expected = _clean(ADMIN_API_KEY)
    if not expected:
        # Fail closed: with no key configured, nobody opens the panel.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Chave do painel não configurada no servidor (ADMIN_API_KEY).")
    if not key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Header X-Admin-Key ausente.")
    if not secrets.compare_digest(_clean(key).encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chave do painel inválida.")
