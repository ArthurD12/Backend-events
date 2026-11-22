"""Consulta para otros módulos: quiénes pueden coordinar un evento (HU10, R-EVT-2).

Usuarios activos con rol de administrador o encargado de eventos. Solo devuelve el id y el
nombre: nada de correos ni otros datos personales.
"""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.identity.application.ports.user_repository import UserRepository
from local_eventos.modules.identity.domain.permissions import Role

COORDINATOR_ROLES = (Role.ADMIN, Role.EVENTS_MANAGER)


@dataclass(frozen=True)
class Coordinator:
    id: UUID
    name: str


class ListCoordinators:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def __call__(self) -> list[Coordinator]:
        users = await self._users.list(include_inactive=False)
        return [Coordinator(id=u.id, name=u.name) for u in users if u.role in COORDINATOR_ROLES]
