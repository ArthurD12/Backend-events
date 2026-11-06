"""Puerto del repositorio de clientes: la aplicación lo usa, la infraestructura lo implementa."""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.clients.domain.client import Client, Document


class ClientRepository(Protocol):
    async def get(self, client_id: UUID) -> Client | None: ...

    async def get_by_document(self, document: Document) -> Client | None: ...

    async def add(self, client: Client) -> None: ...
