"""Repositorio de clientes en PostgreSQL (HU04): implementa el puerto `ClientRepository`.

Traduce entre la entidad `Client` (reglas del negocio) y la fila `ClientRow` (tabla).
No confirma la transacción: eso lo decide quien abre la sesión, una vez por petición,
para que el cambio del cliente y su auditoría se guarden juntos o no se guarde ninguno.
"""

import re
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial.application.clients.errors import DuplicateDocumentError
from local_eventos.modules.commercial.application.clients.search_text import (
    WITH_ACCENTS,
    WITHOUT_ACCENTS,
    normalize,
)
from local_eventos.modules.commercial.domain.clients.client import (
    Client,
    Document,
    DocumentType,
)
from local_eventos.modules.commercial.domain.clients.document_correction import DocumentCorrection
from local_eventos.modules.commercial.infrastructure.orm_models import (
    ClientRow,
    DocumentCorrectionRow,
)


class SqlAlchemyClientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, client_id: UUID) -> Client | None:
        row = await self._session.get(ClientRow, client_id)
        return _to_client(row) if row is not None else None

    async def get_by_document(self, document: Document) -> Client | None:
        row = await self._session.scalar(
            select(ClientRow).where(
                ClientRow.document_type == document.type.value,
                ClientRow.document_number == document.number,
            )
        )
        return _to_client(row) if row is not None else None

    async def add(self, client: Client) -> None:
        self._session.add(_to_row(client))
        await self._flush()

    async def update(self, client: Client) -> None:
        row = await self._session.get(ClientRow, client.id)
        if row is None:
            raise LookupError(f"El cliente {client.id} no existe en la base de datos.")
        _copy_to_row(client, row)
        await self._flush()

    async def search(self, text: str, *, include_inactive: bool, limit: int) -> list[Client]:
        query = select(ClientRow)
        if not include_inactive:
            query = query.where(ClientRow.active.is_(True))
        if text:
            name_without_accents = func.translate(
                func.lower(ClientRow.name), WITH_ACCENTS, WITHOUT_ACCENTS
            )
            matches = [
                name_without_accents.contains(normalize(text), autoescape=True),
                ClientRow.document_number.contains(text, autoescape=True),
            ]
            phone = re.sub(r"[\s-]", "", text)
            if phone:
                matches.append(ClientRow.phone.contains(phone, autoescape=True))
            query = query.where(or_(*matches))
        rows = await self._session.scalars(query.order_by(ClientRow.name).limit(limit))
        return [_to_client(row) for row in rows]

    async def add_document_correction(self, correction: DocumentCorrection) -> None:
        self._session.add(
            DocumentCorrectionRow(
                client_id=correction.client_id,
                previous_document_type=correction.previous.type.value,
                previous_document_number=correction.previous.number,
                new_document_type=correction.new.type.value,
                new_document_number=correction.new.number,
                reason=correction.reason,
                corrected_by=correction.corrected_by,
                corrected_at=correction.corrected_at,
            )
        )
        await self._flush()

    async def _flush(self) -> None:
        """Envía los cambios a PostgreSQL. Si el documento ya existe, lo traduce a error de negocio.

        La aplicación ya revisa duplicados antes de guardar; esto cubre el caso en que dos
        personas registran el mismo documento al mismo tiempo (la restricción UNIQUE gana).
        """
        try:
            await self._session.flush()
        except IntegrityError as error:
            if "uq_commercial_clients_document_type" in str(error.orig):
                raise DuplicateDocumentError() from error
            raise


def _to_client(row: ClientRow) -> Client:
    return Client(
        id=row.id,
        name=row.name,
        document=Document(DocumentType(row.document_type), row.document_number),
        phone=row.phone,
        email=row.email,
        address=row.address,
        active=row.active,
    )


def _to_row(client: Client) -> ClientRow:
    row = ClientRow(id=client.id)
    _copy_to_row(client, row)
    return row


def _copy_to_row(client: Client, row: ClientRow) -> None:
    row.name = client.name
    row.document_type = client.document.type.value
    row.document_number = client.document.number
    row.phone = client.phone
    row.email = client.email
    row.address = client.address
    row.active = client.active
