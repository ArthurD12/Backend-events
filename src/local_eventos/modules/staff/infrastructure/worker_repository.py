"""Repositorio de trabajadores en PostgreSQL (HU15): implementa `WorkerRepository`."""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.staff.application.errors import DocumentTakenError
from local_eventos.modules.staff.application.ports.worker_repository import WorkerFilters
from local_eventos.modules.staff.application.search_text import (
    WITH_ACCENTS,
    WITHOUT_ACCENTS,
    normalize,
)
from local_eventos.modules.staff.domain.worker import (
    DocumentType,
    Worker,
    WorkerDocument,
    WorkerFunction,
    WorkerType,
)
from local_eventos.modules.staff.infrastructure.orm_models import WorkerRow


class SqlAlchemyWorkerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, worker_id: UUID) -> Worker | None:
        row = await self._session.get(WorkerRow, worker_id)
        return _to_worker(row) if row is not None else None

    async def get_many(self, worker_ids: Collection[UUID]) -> list[Worker]:
        if not worker_ids:
            return []
        rows = await self._session.scalars(
            select(WorkerRow).where(WorkerRow.id.in_(list(worker_ids)))
        )
        return [_to_worker(row) for row in rows]

    async def get_by_document(self, document: WorkerDocument) -> Worker | None:
        row = await self._session.scalar(
            select(WorkerRow).where(
                WorkerRow.document_type == document.type.value,
                WorkerRow.document_number == document.number,
            )
        )
        return _to_worker(row) if row is not None else None

    async def add(self, worker: Worker) -> None:
        row = WorkerRow(id=worker.id, created_by=worker.created_by, created_at=worker.created_at)
        _copy_to_row(worker, row)
        self._session.add(row)
        await self._flush()

    async def update(self, worker: Worker) -> None:
        row = await self._session.get(WorkerRow, worker.id)
        if row is None:
            raise LookupError(f"El trabajador {worker.id} no existe en la base de datos.")
        _copy_to_row(worker, row)
        await self._flush()

    async def search(self, filters: WorkerFilters) -> list[Worker]:
        rows = await self._session.scalars(
            select(WorkerRow).where(*_conditions(filters)).order_by(WorkerRow.name, WorkerRow.id)
        )
        return [_to_worker(row) for row in rows]

    async def _flush(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as error:
            # Dos personas registrando el mismo documento a la vez: gana una (CA-15.2).
            if "uq_staff_workers_document_type" in str(error.orig):
                raise DocumentTakenError() from error
            raise


def _conditions(filters: WorkerFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.text:
        name = func.translate(func.lower(WorkerRow.name), WITH_ACCENTS, WITHOUT_ACCENTS)
        conditions.append(
            or_(
                name.contains(normalize(filters.text), autoescape=True),
                WorkerRow.document_number.contains(filters.text.upper(), autoescape=True),
            )
        )
    if filters.function is not None:
        conditions.append(WorkerRow.function == filters.function.value)
    if filters.worker_type is not None:
        conditions.append(WorkerRow.worker_type == filters.worker_type.value)
    if filters.active is not None:
        conditions.append(WorkerRow.active.is_(filters.active))
    return conditions


def _copy_to_row(worker: Worker, row: WorkerRow) -> None:
    row.name = worker.name
    row.document_type = worker.document.type.value
    row.document_number = worker.document.number
    row.phone = worker.phone
    row.function = worker.function.value
    row.worker_type = worker.worker_type.value
    row.reference_rate_cents = worker.reference_rate_cents
    row.active = worker.active
    row.updated_by = worker.updated_by
    row.updated_at = worker.updated_at


def _to_worker(row: WorkerRow) -> Worker:
    return Worker(
        id=row.id,
        name=row.name,
        document=WorkerDocument(DocumentType(row.document_type), row.document_number),
        phone=row.phone,
        function=WorkerFunction(row.function),
        worker_type=WorkerType(row.worker_type),
        reference_rate_cents=row.reference_rate_cents,
        active=row.active,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )
