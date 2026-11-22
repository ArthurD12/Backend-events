"""Seguridad concreta: Argon2 para contraseñas, JWT para el access token y reloj del sistema.

Implementa los puertos de `application/ports/security.py` (ADR 0001).
"""

from datetime import UTC, datetime
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from local_eventos.modules.identity.application.ports.security import AccessTokenClaims

_ALGORITHM = "HS256"


class AuthSettings(BaseSettings):
    """`JWT_SECRET` es obligatorio: sin él la API no firma tokens (nunca hay clave por defecto)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: SecretStr = Field(min_length=32)


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._hash = PasswordHash.recommended()
        self._dummy_hash = self._hash.hash("clave-ficticia-para-igualar-tiempos")

    def hash(self, password: str) -> str:
        return self._hash.hash(password)

    def verify(self, password: str, password_hash: str | None) -> bool:
        if password_hash is None:
            self._hash.verify(password, self._dummy_hash)
            return False
        return self._hash.verify(password, password_hash)


class JwtTokenIssuer:
    def __init__(self, secret: str) -> None:
        self._secret = secret

    def issue(self, *, user_id: UUID, role: str, expires_at: datetime) -> str:
        payload = {"sub": str(user_id), "role": role, "exp": expires_at}
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def read(self, token: str) -> AccessTokenClaims | None:
        try:
            payload = jwt.decode(
                token, self._secret, algorithms=[_ALGORITHM], options={"require": ["exp", "sub"]}
            )
            return AccessTokenClaims(user_id=UUID(str(payload["sub"])))
        except (jwt.InvalidTokenError, ValueError):
            return None


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
