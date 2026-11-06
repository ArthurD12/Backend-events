"""Repositorio de clientes en memoria para probar los casos de uso sin base de datos."""

from uuid import UUID

from local_eventos.modules.clients.domain.client import Client, Document


class InMemoryClientRepository:
    def __init__(self) -> None:
        self.clients: dict[UUID, Client] = {}

    async def get(self, client_id: UUID) -> Client | None:
        return self.clients.get(client_id)

    async def get_by_document(self, document: Document) -> Client | None:
        return next((c for c in self.clients.values() if c.document == document), None)

    async def add(self, client: Client) -> None:
        self.clients[client.id] = client
