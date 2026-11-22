"""Sesión de un usuario: permite renovar el acceso sin volver a escribir la contraseña (HU01).

Solo se guarda el hash del refresh token, nunca el token. La sesión se vence tras 30 minutos
sin usarse (CA-01.6) y, en cualquier caso, a las 12 horas de iniciada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

IDLE_TIMEOUT = timedelta(minutes=30)
MAX_LIFETIME = timedelta(hours=12)


@dataclass
class Session:
    id: UUID
    user_id: UUID
    token_hash: str
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    @classmethod
    def start(cls, *, user_id: UUID, token_hash: str, now: datetime) -> Session:
        return cls(
            id=uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            created_at=now,
            last_used_at=now,
            expires_at=now + MAX_LIFETIME,
        )

    def is_usable(self, now: datetime) -> bool:
        return (
            self.revoked_at is None
            and now < self.expires_at
            and now - self.last_used_at < IDLE_TIMEOUT
        )

    def rotate(self, *, token_hash: str, now: datetime) -> None:
        """Cambia el token en cada uso: un token robado y ya usado deja de servir."""
        self.token_hash = token_hash
        self.last_used_at = now

    def revoke(self, now: datetime) -> None:
        if self.revoked_at is None:
            self.revoked_at = now
