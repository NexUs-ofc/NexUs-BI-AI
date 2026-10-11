"""Authentication dependency used by the chat routes.

Every request needs:
- X-API-Key header: identifies the client application (see api_key.py). In a website this key is visible
  in the browser, so it only identifies the app; the real protection is the token below.
- Authorization: Bearer <JWT> header: the access token returned by the Auth service (NexUs-Auth) when the
  user logs in on the website (channel PLATFORM). It is validated here by its signature.

Business rule of the MVP: the reports are the same for every company. Authentication only guarantees
that the caller is a real, ACTIVE company: the token must be of a COMPANY profile and the company must
exist in the Auth PostgreSQL database. ADMIN, HOUSEHOLD and STORE profiles cannot use the BI chat.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.api_key import verify_api_key
from app.auth.jwt_handler import InvalidTokenError, decode_token
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
    except (TypeError, ValueError) as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token sem identificação de perfil.") from error

    # 2) Only company profiles use the BI chat
    if claims.get("profile_type") != COMPANY_PROFILE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas perfis de empresa podem usar o NexUs BI.")

    # 3) The company must exist and be active in the Auth database
    try:
        company_id = find_active_company_id(profile_id)
    except Exception as error:  # noqa: BLE001 - database offline, wrong URL...
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Não foi possível verificar a empresa no momento."
        ) from error
    if company_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Empresa não encontrada ou inativa.")

    return CurrentUser(profile_id=profile_id, company_id=company_id)
