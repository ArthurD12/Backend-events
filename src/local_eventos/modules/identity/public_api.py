"""Superficie pública del módulo identity: única vía de uso por otros módulos.

Los demás módulos protegen sus rutas con `require_permission(Permission.X)` y, cuando
necesiten auditar (RN03), reciben al `CurrentUser`. Nunca importan nada interno de identity.
"""

from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.identity import composition
from local_eventos.modules.identity.application.use_cases.coordinators import (
    Coordinator,
    ListCoordinators,
)
from local_eventos.modules.identity.application.use_cases.user_names import UserNames
from local_eventos.modules.identity.domain.permissions import Permission
from local_eventos.modules.identity.presentation.dependencies import (
    CurrentUser,
    get_current_user,
    require_permission,
)


class CoordinatorLookup(Protocol):
    """Usuarios activos que pueden coordinar un evento (administrador o encargado de eventos)."""

    async def __call__(self) -> list[Coordinator]: ...


class UserNamesLookup(Protocol):
    """Nombre de cada usuario pedido, activo o no. Los IDs que no existen no vienen."""

    async def __call__(self, user_ids: Iterable[UUID]) -> dict[UUID, str]: ...


def coordinator_lookup(session: AsyncSession) -> CoordinatorLookup:
    return ListCoordinators(composition.user_repository(session))


def user_names(session: AsyncSession) -> UserNamesLookup:
    return UserNames(composition.user_repository(session))


__all__ = [
    "Coordinator",
    "CoordinatorLookup",
    "CurrentUser",
    "Permission",
    "UserNamesLookup",
    "coordinator_lookup",
    "get_current_user",
    "require_permission",
    "user_names",
]
