"""Búsqueda de clientes por nombre, documento o teléfono, para otros módulos (solo lectura)."""

from local_eventos.modules.commercial.application.clients.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.commercial.application.clients.use_cases.get_client_summary import (
    ClientSummary,
)


class SearchClientSummaries:
    def __init__(self, clients: ClientRepository) -> None:
        self._clients = clients

    async def __call__(self, text: str, limit: int = 10) -> list[ClientSummary]:
        found = await self._clients.search(text, include_inactive=True, limit=limit)
        return [
            ClientSummary(
                id=c.id,
                name=c.name,
                document_type=c.document.type.value,
                document_number=c.document.number,
                phone=c.phone,
                email=c.email,
                active=c.active,
            )
            for c in found
        ]
