"""Dependências de autenticação das rotas do gerador (mesmo esquema do NexUs-AI).

Toda rota exige:
- X-API-Key: identifica a aplicação cliente (interface web).
- Authorization: Bearer <JWT> emitido pelo NexUs-Auth, validado pela assinatura.

Permissões por tipo de perfil (claim `profile_type`), configuráveis no .env:
- leitura (listar, ver JSON/HTML/PDF): REPORT_READ_PROFILES  (padrão COMPANY,ADMIN)
- escrita (gerar, publicar):           REPORT_WRITE_PROFILES (padrão ADMIN)
"""
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from report_generator.auth.api_key import verify_api_key
from report_generator.auth.jwt_handler import InvalidTokenError, decode_token
from report_generator.config import READ_PROFILES, WRITE_PROFILES

_bearer = HTTPBearer(auto_error=False)
_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


class CurrentUser(BaseModel):
    profile_id: int
    profile_type: str


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
    _api_key: Annotated[None, Depends(verify_api_key)],
) -> CurrentUser:
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token Bearer ausente.", headers=_UNAUTHORIZED)
    try:
        claims = decode_token(credentials.credentials)
        profile_id = int(claims["sub"])
    except InvalidTokenError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error), headers=_UNAUTHORIZED) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token sem identificação de perfil.") from error
    return CurrentUser(profile_id=profile_id, profile_type=str(claims.get("profile_type", "")))


def require_reader(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    if user.profile_type not in READ_PROFILES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Este perfil não pode ver relatórios.")
    return user


def require_writer(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    if user.profile_type not in WRITE_PROFILES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Este perfil não pode gerar ou publicar relatórios.")
    return user
