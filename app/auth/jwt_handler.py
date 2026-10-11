"""JWT validation (copied from NexUs-AI and simplified).

This API only VALIDATES tokens; the Auth microservice issues them (HS256 with a shared secret).
Claims checked: signature, expiration ("exp"), issuer ("iss" = nexus-auth) and "sub" (profile id).
The token is the same for the website (channel PLATFORM) and the mobile app; the channel only matters
at login time, inside the Auth service.

Test token for local development (needs JWT_SECRET_BASE64 in .env), run from the project root, passing
the id of an ACTIVE COMPANY profile that exists in the Auth database:
    python -m app.auth.jwt_handler <profile_id>
"""
import base64
import binascii
import re
import sys
import time

import jwt

from app.config import JWT_ALGORITHM, JWT_ISSUER, JWT_SECRET


class InvalidTokenError(Exception):
    """Token missing, malformed, expired, from another issuer or badly signed."""


def secret_bytes(secret: str) -> bytes:
    """Turn the configured secret into the HMAC key bytes.

    The Auth service keeps the secret in Base64 (JWT_SECRET_BASE64); hex is also accepted. The hex check
    comes first because 64 hex characters are also valid Base64 and would decode to the wrong bytes.
    """
    if re.fullmatch(r"[0-9a-fA-F]{64}", secret):
        return bytes.fromhex(secret)
    try:
        return base64.b64decode(secret, validate=True)
    except (binascii.Error, ValueError) as error:
        raise InvalidTokenError("JWT_SECRET_BASE64 não é Base64 válido (nem hex de 64 caracteres).") from error


def decode_token(token: str) -> dict:
    """Return the token claims or raise InvalidTokenError (messages in Portuguese, shown to the client)."""
    if not JWT_SECRET:
        raise InvalidTokenError("JWT_SECRET_BASE64 não configurada no servidor.")
    try:
        return jwt.decode(
            token,
            secret_bytes(JWT_SECRET),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as error:
        raise InvalidTokenError("Token expirado.") from error
    except jwt.InvalidIssuerError as error:
        raise InvalidTokenError("Token emitido por outra origem.") from error
    except jwt.InvalidSignatureError as error:
        raise InvalidTokenError("Assinatura do token inválida.") from error
    except jwt.InvalidTokenError as error:
        raise InvalidTokenError("Token inválido.") from error


def create_test_token(profile_id: str, hours: int = 8) -> str:
    """Development only: sign a token like the Auth service would, to test the API in /docs."""
    now = int(time.time())
    claims = {"iss": JWT_ISSUER, "sub": str(profile_id), "iat": now, "exp": now + hours * 3600,
              "profile_type": "COMPANY"}
    return jwt.encode(claims, secret_bytes(JWT_SECRET), algorithm=JWT_ALGORITHM)


if __name__ == "__main__":
    profile = sys.argv[1] if len(sys.argv) > 1 else "1"
    print(f"Token de teste para o perfil {profile} (válido por 8h):")
    print(create_test_token(profile))
