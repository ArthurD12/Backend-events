"""Casos de uso: desactivar y reactivar un cliente sin eliminarlo (HU04, RN02)."""

from uuid import UUID

from local_eventos.modules.clients.application.errors import ClientNotFoundError
from local_eventos.modules.clients.application.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.clients.domain.client import Client


class DeactivateClient:
    def __init__(self, clients: ClientRepository) -> None:
        self._clients = clients

    async def __call__(self, client_id: UUID) -> Client:
        client = await _get_or_fail(self._clients, client_id)
        client.deactivate()
        await self._clients.update(client)
        return client


class ActivateClient:
    def __init__(self, clients: ClientRepository) -> None:
        self._clients = clients

    async def __call__(self, client_id: UUID) -> Client:
        client = await _get_or_fail(self._clients, client_id)
        client.activate()
        await self._clients.update(client)
        return client


async def _get_or_fail(clients: ClientRepository, client_id: UUID) -> Client:
    client = await clients.get(client_id)
    if client is None:
        raise ClientNotFoundError()
    return client
