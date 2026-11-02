"""Authentication dependency used by the chat routes.

Every request needs:
- X-API-Key header: identifies the client application (see api_key.py). In a website this key is visible
  in the browser, so it only identifies the app; the real protection is the token below.
- Authorization: Bearer <JWT> header: the access token returned by the Auth service (NexUs-Auth) when the
  user logs in on the website (channel PLATFORM). It is validated here by its signature.

Business rule of the MVP: the reports are the same for every company. Only the profiles in CHAT_PROFILES
(COMPANY and ADMIN by default, the same that read the reports) use the BI chat and the rankings.
A COMPANY must also exist and be ACTIVE in the Auth PostgreSQL database; ADMIN skips that query.
HOUSEHOLD and STORE profiles get 403.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.api_key import verify_api_key
from app.auth.jwt_handler import InvalidTokenError, decode_token
from app.config import CHAT_PROFILES, REQUIRE_ACTIVE_COMPANY
from app.observability import trace
from app.repository.company_repository import find_active_company_id
from app.schemas.api import CurrentUser

COMPANY_PROFILE = "COMPANY"

_bearer = HTTPBearer(auto_error=False)
_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
    _api_key: Annotated[None, Depends(verify_api_key)],
) -> CurrentUser:
    # 1) Token present and valid (signature, expiration, issuer)
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token Bearer ausente.", headers=_UNAUTHORIZED)
    try:
        claims = decode_token(credentials.credentials)
        profile_id = int(claims["sub"])
    except InvalidTokenError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error), headers=_UNAUTHORIZED) from error
    except (TypeError, ValueError, KeyError) as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token sem identificação de perfil.") from error

    # 2) Only the allowed profiles
    profile_type = str(claims.get("profile_type", "")).upper()
    if profile_type not in CHAT_PROFILES:
        trace.log("auth.negado", 30, perfil=profile_type or "ausente")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Seu perfil não tem acesso ao NexUs BI.")
    if profile_type != COMPANY_PROFILE:
        trace.log("auth.ok", perfil=profile_type)
        return CurrentUser(profile_id=profile_id)

    # 3) A company must exist and be active in the Auth database (CHAT_REQUIRE_ACTIVE_COMPANY=false skips it: tests only)
    if not REQUIRE_ACTIVE_COMPANY:
        trace.log("auth.ok", 30, perfil=profile_type, empresa_ativa="NAO VERIFICADA (CHAT_REQUIRE_ACTIVE_COMPANY=false)")
        return CurrentUser(profile_id=profile_id)
    try:
        with trace.step("auth.postgres", service="postgres", perfil=profile_type) as info:
            company_id = find_active_company_id(profile_id)
            info["empresa_ativa"] = company_id is not None
    except Exception as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Serviço indisponível — PostgreSQL do Auth: não foi possível verificar a empresa no momento.",
        ) from error
    if company_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Empresa não encontrada ou inativa.")
    return CurrentUser(profile_id=profile_id, company_id=company_id)
