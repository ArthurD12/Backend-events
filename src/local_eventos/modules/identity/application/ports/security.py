"""Puertos de seguridad: cifrar contraseñas, firmar tokens y leer la hora.

La aplicación no sabe qué algoritmo se usa: eso lo decide `infrastructure` (Argon2 y JWT).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str | None) -> bool:
        """Con `password_hash=None` igual hace el trabajo de verificar y devuelve False.

        Así responder "acceso rechazado" tarda lo mismo exista o no el correo.
        """
        ...


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: UUID


class TokenIssuer(Protocol):
    def issue(self, *, user_id: UUID, role: str, expires_at: datetime) -> str: ...

    def read(self, token: str) -> AccessTokenClaims | None:
        """Devuelve los datos si la firma es válida y no venció; si no, `None`."""
        ...


class Clock(Protocol):
    def now(self) -> datetime:
        """Hora actual en UTC (AGENTS.md, regla 4)."""
        ...
