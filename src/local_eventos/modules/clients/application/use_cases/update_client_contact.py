"""Caso de uso: actualizar los datos de contacto de un cliente (HU04)."""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.clients.application.errors import ClientNotFoundError
from local_eventos.modules.clients.application.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.clients.domain.client import Client


@dataclass(frozen=True)
class UpdateClientContactCommand:
    client_id: UUID
    name: str
    phone: str
    email: str | None = None
    address: str | None = None


class UpdateClientContact:
    def __init__(self, clients: ClientRepository) -> None:
        self._clients = clients

    async def __call__(self, command: UpdateClientContactCommand) -> Client:
        client = await self._clients.get(command.client_id)
        if client is None:
            raise ClientNotFoundError()
        client.update_contact(
            name=command.name,
            phone=command.phone,
            email=command.email,
            address=command.address,
        )
        await self._clients.update(client)
        return client
