"""Puerto: cómo la aplicación guarda y lee usuarios. La base de datos lo implementa."""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.identity.domain.user import User


class UserRepository(Protocol):
    async def get(self, user_id: UUID) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None:
        """Busca por correo exacto, ya normalizado en minúsculas."""
        ...

    async def add(self, user: User) -> None: ...

    async def update(self, user: User) -> None: ...

    async def list(self, *, include_inactive: bool) -> list[User]:
        """Devuelve los usuarios ordenados por nombre."""
        ...

    async def count_active_admins(self) -> int: ...
