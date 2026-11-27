"""Repositorio de trabajadores en PostgreSQL (HU15): implementa `WorkerRepository`.

Traduce entre el agregado `Worker`/`WorkerAudit` y las filas ORM mediante `mappers.py`;
nunca devuelve filas al exterior. No confirma la transacción: eso lo decide quien abre
la sesión, para que la ficha y su auditoría se guarden juntas o no se guarde ninguna
(plan §4). Si dos altas simultáneas pasan la comprobación de la aplicación, la
restricción UNIQUE de PostgreSQL decide: la perdedora recibe `DuplicateDocumentError`
(plan §6.4, T-12).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from local_eventos.modules.staff.application.errors import DuplicateDocumentError
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerPage,
    WorkerRef,
)
from local_eventos.modules.staff.application.search_text import (
    normalize_document,
    normalize_name,
)
from local_eventos.modules.staff.domain.audit import WorkerAudit
from local_eventos.modules.staff.domain.document import Document
from local_eventos.modules.staff.domain.enums import WorkerFunction, WorkerStatus
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.mappers import (
    apply_worker_to_row,
    audit_to_row,
    worker_from_row,
    worker_to_row,
)
from local_eventos.modules.staff.infrastructure.orm_models import (
    StaffWorkerRow,
)

# Misma tabla de equivalencias que usa la búsqueda de clientes: `lower()` + `translate()`
# en PostgreSQL producen la misma forma que `normalize_name` en memoria. No requiere
# extensiones ni columnas adicionales (plan §8.2).
_WITH_ACCENTS = "áéíóúàèìòùäëïöüñ"
_WITHOUT_ACCENTS = "aeiouaeiouaeioun"


class SqlAlchemyWorkerRepository:
    """Implementación async del puerto sobre la sesión de SQLAlchemy de la petición."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, worker: Worker, audit: WorkerAudit) -> None:
        row = await self._session.get(StaffWorkerRow, worker.id)
        if row is None:
            self._session.add(worker_to_row(worker))
        else:
            apply_worker_to_row(worker, row)
        # La ficha se escribe antes que su auditoría para que la FK siempre resuelva.
        await self._flush(worker.document)
        self._session.add(audit_to_row(audit))
        await self._flush(worker.document)

    async def get(self, worker_id: UUID) -> Worker | None:
        row = await self._session.get(StaffWorkerRow, worker_id)
        return worker_from_row(row) if row is not None else None

    async def get_for_update(self, worker_id: UUID) -> Worker | None:
        row = await self._session.scalar(
            select(StaffWorkerRow).where(StaffWorkerRow.id == worker_id).with_for_update()
        )
        return worker_from_row(row) if row is not None else None

    async def get_by_document(self, document: Document) -> Worker | None:
        row = await self._session.scalar(
            select(StaffWorkerRow).where(
                StaffWorkerRow.document_type == document.type.value,
                StaffWorkerRow.document_number == document.number,
            )
        )
        return worker_from_row(row) if row is not None else None

    async def search(
        self,
        *,
        text: str,
        function: WorkerFunction | None,
        status: WorkerStatus | None,
        page: int,
        page_size: int,
    ) -> WorkerPage:
        filters = self._filters(text=text, function=function, status=status)

        total_query = select(func.count()).select_from(StaffWorkerRow).where(*filters)
        total = int(await self._session.scalar(total_query) or 0)

        rows_query = (
            select(StaffWorkerRow)
            .where(*filters)
            .order_by(
                func.lower(StaffWorkerRow.name),
                StaffWorkerRow.name,
                StaffWorkerRow.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = await self._session.scalars(rows_query)
        return WorkerPage(
            items=[worker_from_row(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def lookup(self, worker_id: UUID) -> WorkerRef | None:
        row = (
            await self._session.execute(
                select(
                    StaffWorkerRow.id,
                    StaffWorkerRow.name,
                    StaffWorkerRow.worker_function,
                    StaffWorkerRow.function_description,
                    StaffWorkerRow.status,
                ).where(StaffWorkerRow.id == worker_id)
            )
        ).first()
        if row is None:
            return None
        return WorkerRef(
            id=row.id,
            name=row.name,
            function=None if row.worker_function is None else WorkerFunction(row.worker_function),
            function_description=row.function_description,
            status=WorkerStatus(row.status),
        )

    async def list_active(
        self, function: WorkerFunction | None = None
    ) -> list[WorkerRef]:
        query = select(
            StaffWorkerRow.id,
            StaffWorkerRow.name,
            StaffWorkerRow.worker_function,
            StaffWorkerRow.function_description,
            StaffWorkerRow.status,
        ).where(StaffWorkerRow.status == WorkerStatus.ACTIVE.value)
        if function is not None:
            query = query.where(StaffWorkerRow.worker_function == function.value)
        query = query.order_by(
            func.lower(StaffWorkerRow.name), StaffWorkerRow.name, StaffWorkerRow.id
        )
        rows = await self._session.execute(query)
        return [
            WorkerRef(
                id=row.id,
                name=row.name,
                function=(
                    None
                    if row.worker_function is None
                    else WorkerFunction(row.worker_function)
                ),
                function_description=row.function_description,
                status=WorkerStatus(row.status),
            )
            for row in rows
        ]

    async def _flush(self, document: Document) -> None:
        """Envía los cambios a PostgreSQL. Si el documento ya existe, error de negocio.

        La aplicación ya revisa duplicados antes de guardar; esto cubre el caso en que dos
        altas simultáneas pasan esa comprobación y la restricción UNIQUE gana. La
        transacción la cierra quien abrió la sesión, que hace rollback al propagarse la
        excepción (mismo patrón que `commercial`/`catalog`), de modo que la API responde 409.
        """
        try:
            await self._session.flush()
        except IntegrityError as error:
            if "uq_staff_workers_document" in str(error.orig):
                raise DuplicateDocumentError(document) from error
            raise

    @staticmethod
    def _filters(
        *, text: str, function: WorkerFunction | None, status: WorkerStatus | None
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        cleaned = text.strip()
        if cleaned:
            matches: list[ColumnElement[bool]] = []
            normalized_name = normalize_name(cleaned)
            if normalized_name:
                name_expression = func.translate(
                    func.lower(StaffWorkerRow.name), _WITH_ACCENTS, _WITHOUT_ACCENTS
                )
                matches.append(name_expression.ilike(_contains(normalized_name), escape="\\"))
            normalized_document = normalize_document(cleaned)
            if normalized_document:
                matches.append(
                    StaffWorkerRow.document_number.ilike(
                        _contains(normalized_document), escape="\\"
                    )
                )
            if matches:
                filters.append(or_(*matches))
        if function is not None:
            filters.append(StaffWorkerRow.worker_function == function.value)
        if status is not None:
            filters.append(StaffWorkerRow.status == status.value)
        return filters


def _contains(value: str) -> str:
    """Patrón `%valor%` escapando los comodines de `ILIKE` para que sean literales."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
