"""Superficie pública del módulo identity: única vía de uso por otros módulos.

Los demás módulos protegen sus rutas con `require_permission(Permission.X)` y, cuando
necesiten auditar (RN03), reciben al `CurrentUser`. Nunca importan nada interno de identity.
"""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.identity import composition
from local_eventos.modules.identity.application.use_cases.coordinators import (
    Coordinator,
    ListCoordinators,
)
from local_eventos.modules.identity.domain.permissions import Permission
from local_eventos.modules.identity.presentation.dependencies import (
    CurrentUser,
    get_current_user,
    require_permission,
)


class CoordinatorLookup(Protocol):
    """Usuarios activos que pueden coordinar un evento (administrador o encargado de eventos)."""

    async def __call__(self) -> list[Coordinator]: ...


def coordinator_lookup(session: AsyncSession) -> CoordinatorLookup:
    return ListCoordinators(composition.user_repository(session))


__all__ = [
    "Coordinator",
    "CoordinatorLookup",
    "CurrentUser",
    "Permission",
    "coordinator_lookup",
    "get_current_user",
    "require_permission",
]
