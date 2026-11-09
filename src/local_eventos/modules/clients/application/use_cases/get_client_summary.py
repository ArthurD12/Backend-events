"""Consulta para otros módulos: datos básicos de un cliente (HU04 → HU07, HU09).

Devuelve una copia de solo lectura (`ClientSummary`), nunca la entidad `Client`:
así otro módulo no puede modificar un cliente ni depender de cómo está construido.
"""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.clients.application.ports.client_repository import (
    ClientRepository,
)


@dataclass(frozen=True)
class ClientSummary:
    id: UUID
    name: str
    document_type: str
    document_number: str
    phone: str
    email: str | None
    active: bool


class GetClientSummary:
    def __init__(self, clients: ClientRepository) -> None:
        self._clients = clients

    async def __call__(self, client_id: UUID) -> ClientSummary | None:
        """Devuelve `None` si no existe: cada módulo decide qué error mostrar."""
        client = await self._clients.get(client_id)
        if client is None:
            return None
        return ClientSummary(
            id=client.id,
            name=client.name,
            document_type=client.document.type.value,
            document_number=client.document.number,
            phone=client.phone,
            email=client.email,
            active=client.active,
        )
