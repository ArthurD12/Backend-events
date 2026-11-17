"""Caso de uso: ver la ficha completa de un cliente (HU04)."""

from uuid import UUID

from local_eventos.modules.commercial.application.clients.errors import ClientNotFoundError
from local_eventos.modules.commercial.application.clients.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.commercial.domain.clients.client import Client


class GetClient:
    def __init__(self, clients: ClientRepository) -> None:
        self._clients = clients

    async def __call__(self, client_id: UUID) -> Client:
        client = await self._clients.get(client_id)
        if client is None:
            raise ClientNotFoundError()
        return client
