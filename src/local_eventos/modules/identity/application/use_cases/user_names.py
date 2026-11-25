"""Consulta para otros módulos: el nombre de cada usuario por su ID, activo o no.

Solo lectura y solo el nombre (sin correos ni otros datos personales). Sirve para mostrar quién
registró un pago o un movimiento, aunque ese usuario ya esté desactivado (RN02, RN03).
"""

from collections.abc import Iterable
from uuid import UUID

from local_eventos.modules.identity.application.ports.user_repository import UserRepository


class UserNames:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def __call__(self, user_ids: Iterable[UUID]) -> dict[UUID, str]:
        wanted = set(user_ids)
        if not wanted:
            return {}
        # Darze tiene pocos usuarios: leerlos todos es más simple que una consulta nueva.
        users = await self._users.list(include_inactive=True)
        return {u.id: u.name for u in users if u.id in wanted}
