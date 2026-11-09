"""Caso de uso: buscar clientes por nombre, documento o teléfono (HU04)."""

from dataclasses import dataclass

from local_eventos.modules.clients.application.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.clients.domain.client import Client

MAX_RESULTS = 50


@dataclass(frozen=True)
class SearchClientsQuery:
    text: str = ""
    include_inactive: bool = False


class SearchClients:
    def __init__(self, clients: ClientRepository) -> None:
        self._clients = clients

    async def __call__(self, query: SearchClientsQuery) -> list[Client]:
        text = " ".join(query.text.split())
        return await self._clients.search(
            text, include_inactive=query.include_inactive, limit=MAX_RESULTS
        )
