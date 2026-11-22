"""Usuario de prueba para las APIs protegidas: evita iniciar sesión en cada prueba de módulo.

Uso: `app.dependency_overrides[get_current_user] = signed_in_as(Role.ADMIN)`.
"""

from collections.abc import Awaitable, Callable
from uuid import uuid4

from local_eventos.modules.identity.domain.permissions import Role, permissions_of
from local_eventos.modules.identity.public_api import CurrentUser


def signed_in_as(role: Role) -> Callable[[], Awaitable[CurrentUser]]:
    user = CurrentUser(
        id=uuid4(), name=f"Prueba {role}", role=role, permissions=permissions_of(role)
    )

    async def current_user() -> CurrentUser:
        return user

    return current_user
