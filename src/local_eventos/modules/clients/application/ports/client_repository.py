"""Puerto del repositorio de clientes: la aplicación lo usa, la infraestructura lo implementa."""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.clients.domain.client import Client, Document

from local_eventos.modules.clients.domain.document_correction import DocumentCorrection


class ClientRepository(Protocol):
    async def get(self, client_id: UUID) -> Client | None: ...

    async def get_by_document(self, document: Document) -> Client | None: ...

    async def add(self, client: Client) -> None: ...
    async def update(self, client: Client) -> None: ...

    async def search(
        self, text: str, *, include_inactive: bool, limit: int
    ) -> list[Client]:
        """Clientes cuyo nombre, documento o teléfono contienen `text`, ordenados por nombre.

        Sin distinguir mayúsculas. Los espacios y guiones del texto se ignoran al comparar
        el teléfono. Un texto vacío devuelve todos los clientes.
        """
        ...

    async def add_document_correction(self, correction: DocumentCorrection) -> None: ...
