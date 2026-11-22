"""Puerto: cómo la aplicación guarda y lee sesiones. La base de datos lo implementa."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from local_eventos.modules.identity.domain.session import Session


class SessionRepository(Protocol):
    async def add(self, session: Session) -> None: ...

    async def get_by_token_hash(self, token_hash: str) -> Session | None: ...

    async def update(self, session: Session) -> None: ...

    async def revoke_all_for_user(self, user_id: UUID, now: datetime) -> None:
        """Cierra todas las sesiones abiertas del usuario (al desactivarlo o cambiar su clave)."""
        ...
