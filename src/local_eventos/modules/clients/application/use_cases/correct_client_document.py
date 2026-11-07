"""Caso de uso: corregir el documento de un cliente con registro de auditoría (HU04, RN03)."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from local_eventos.modules.clients.application.errors import (
    ClientNotFoundError,
    DocumentUnchangedError,
    DuplicateDocumentError,
)
from local_eventos.modules.clients.application.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.clients.domain.client import Client, Document, DocumentType
from local_eventos.modules.clients.domain.document_correction import DocumentCorrection


@dataclass(frozen=True)
class CorrectClientDocumentCommand:
    client_id: UUID
    document_type: DocumentType
    document_number: str
    reason: str
    corrected_by: UUID


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CorrectClientDocument:
    def __init__(
        self, clients: ClientRepository, now: Callable[[], datetime] = _utc_now
    ) -> None:
        self._clients = clients
        self._now = now

    async def __call__(self, command: CorrectClientDocumentCommand) -> Client:
        client = await self._clients.get(command.client_id)
        if client is None:
            raise ClientNotFoundError()

        new_document = Document(command.document_type, command.document_number.strip())
        if new_document == client.document:
            raise DocumentUnchangedError()
        if await self._clients.get_by_document(new_document) is not None:
            raise DuplicateDocumentError()

        previous = client.correct_document(
            document_type=new_document.type,
            document_number=new_document.number,
            reason=command.reason,
        )
        await self._clients.update(client)
        await self._clients.add_document_correction(
            DocumentCorrection(
                client_id=client.id,
                previous=previous,
                new=client.document,
                reason=command.reason.strip(),
                corrected_by=command.corrected_by,
                corrected_at=self._now(),
            )
        )
        return client
