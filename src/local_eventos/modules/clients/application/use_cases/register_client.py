"""Caso de uso: registrar un cliente (HU04)."""

from dataclasses import dataclass

from local_eventos.modules.clients.application.errors import DuplicateDocumentError
from local_eventos.modules.clients.application.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.clients.domain.client import Client, DocumentType


@dataclass(frozen=True)
class RegisterClientCommand:
    name: str
    document_type: DocumentType
    document_number: str
    phone: str
    email: str | None = None
    address: str | None = None


class RegisterClient:
    def __init__(self, clients: ClientRepository) -> None:
        self._clients = clients

    async def __call__(self, command: RegisterClientCommand) -> Client:
        client = Client.register(
            name=command.name,
            document_type=command.document_type,
            document_number=command.document_number,
            phone=command.phone,
            email=command.email,
            address=command.address,
        )
        if await self._clients.get_by_document(client.document) is not None:
            raise DuplicateDocumentError()
        await self._clients.add(client)
        return client
