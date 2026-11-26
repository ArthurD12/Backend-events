"""Repositorio de asignaciones en PostgreSQL (HU17, T-15): implementa `AssignmentRepository`.

Traduce entre el agregado `Assignment`/`AssignmentAudit` y las filas ORM mediante
`mappers.py`; nunca devuelve filas al exterior. No confirma la transacción: la
gestión la decide quien abre la sesión, para que la asignación y su auditoría se
guarden juntas o no se guarde ninguna (plan §5.5).

El no-solape es una garantía de PostgreSQL (restricción de exclusión
`staff_assignments_no_overlap`). Si dos transacciones compiten, la perdedora recibe
SQLSTATE `23P01` y aquí se traduce a `AssignmentOverlapError` sin conflictos: dentro
de la transacción abortada ya no se puede consultar el evento. El orden de bloqueo
es siempre `staff_workers` → `staff_assignments` (plan §5.5).

El módulo no consulta tablas de `commercial` (regla 3): las vistas de lectura dejan
`event_code`/`event_status` en `None` y la capa de aplicación los completa.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.staff.application.errors import AssignmentOverlapError
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentOverlap,
    AssignmentView,
)
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import AssignmentAudit
from local_eventos.modules.staff.domain.enums import AssignmentStatus
from local_eventos.modules.staff.infrastructure.mappers import (
    assignment_audit_to_row,
    assignment_to_row,
    row_to_assignment,
)
from local_eventos.modules.staff.infrastructure.orm_models import (
    StaffAssignmentRow,
    StaffWorkerRow,
)

_EXCLUSION_SQLSTATE = "23P01"
_NO_OVERLAP_CONSTRAINT = "staff_assignments_no_overlap"


class SqlAlchemyAssignmentRepository:
    """Implementación async del puerto sobre la sesión de SQLAlchemy de la petición."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_worker(self, worker_id: UUID) -> None:
        await self._session.scalar(
            select(StaffWorkerRow.id).where(StaffWorkerRow.id == worker_id).with_for_update()
        )

    async def save(self, assignment: Assignment, audit: AssignmentAudit) -> None:
        row = await self._session.get(StaffAssignmentRow, assignment.id)
        if row is None:
            self._session.add(assignment_to_row(assignment))
        else:
            # Solo campos editables: `event_id` y `worker_id` son inmutables y el
            # trigger de la base los protege si algo intentara cambiarlos.
            row.worker_function = assignment.function.value
            row.function_description = assignment.function_description
            row.start_at = assignment.start_at
            row.end_at = assignment.end_at
            row.pay_cents = assignment.pay.cents
            row.currency = assignment.pay.currency
            row.status = assignment.status.value
            row.occupies = assignment.occupies
        # La asignación se escribe antes que su auditoría para que la FK resuelva.
        await self._flush()
        self._session.add(assignment_audit_to_row(audit))
        await self._flush()

    async def get(self, assignment_id: UUID) -> Assignment | None:
        row = await self._session.get(StaffAssignmentRow, assignment_id)
        return row_to_assignment(row) if row is not None else None

    async def get_for_update(self, assignment_id: UUID) -> Assignment | None:
        row = await self._session.scalar(
            select(StaffAssignmentRow)
            .where(StaffAssignmentRow.id == assignment_id)
            .with_for_update()
        )
        return row_to_assignment(row) if row is not None else None

    async def list_active_overlaps(
        self,
        worker_id: UUID,
        start_at: datetime,
        end_at: datetime,
        *,
        exclude_assignment_id: UUID | None = None,
    ) -> list[AssignmentOverlap]:
        query = select(
            StaffAssignmentRow.id,
            StaffAssignmentRow.event_id,
            StaffAssignmentRow.start_at,
            StaffAssignmentRow.end_at,
        ).where(
            StaffAssignmentRow.worker_id == worker_id,
            StaffAssignmentRow.status == AssignmentStatus.ACTIVE.value,
            StaffAssignmentRow.occupies.is_(True),
            StaffAssignmentRow.start_at < end_at,
            StaffAssignmentRow.end_at > start_at,
        )
        if exclude_assignment_id is not None:
            query = query.where(StaffAssignmentRow.id != exclude_assignment_id)
        rows = (await self._session.execute(query.order_by(StaffAssignmentRow.start_at))).all()
        return [
            AssignmentOverlap(
                id=row.id,
                event_id=row.event_id,
                start_at=row.start_at,
                end_at=row.end_at,
            )
            for row in rows
        ]

    async def list_by_event(self, event_id: UUID) -> list[AssignmentView]:
        rows = await self._session.execute(
            select(StaffAssignmentRow, StaffWorkerRow.name)
            .join(StaffWorkerRow, StaffWorkerRow.id == StaffAssignmentRow.worker_id)
            .where(
                StaffAssignmentRow.event_id == event_id,
                StaffAssignmentRow.status == AssignmentStatus.ACTIVE.value,
            )
            .order_by(StaffAssignmentRow.start_at)
        )
        return [_view(row, worker_name) for row, worker_name in rows]

    async def list_occupying(self, worker_id: UUID) -> list[Assignment]:
        rows = await self._session.scalars(
            select(StaffAssignmentRow).where(
                StaffAssignmentRow.worker_id == worker_id,
                StaffAssignmentRow.status == AssignmentStatus.ACTIVE.value,
                StaffAssignmentRow.occupies.is_(True),
            )
        )
        return [row_to_assignment(row) for row in rows]

    async def release(self, assignments: Sequence[Assignment]) -> None:
        ids = [assignment.id for assignment in assignments]
        if not ids:
            return
        await self._session.execute(
            update(StaffAssignmentRow).where(StaffAssignmentRow.id.in_(ids)).values(occupies=False)
        )

    async def has_active_ending_after(self, worker_id: UUID, moment: datetime) -> bool:
        found = await self._session.scalar(
            select(StaffAssignmentRow.id)
            .where(
                StaffAssignmentRow.worker_id == worker_id,
                StaffAssignmentRow.status == AssignmentStatus.ACTIVE.value,
                StaffAssignmentRow.occupies.is_(True),
                StaffAssignmentRow.end_at > moment,
            )
            .limit(1)
        )
        return found is not None

    async def get_view(self, assignment_id: UUID) -> AssignmentView | None:
        rows = await self._session.execute(
            select(StaffAssignmentRow, StaffWorkerRow.name)
            .join(StaffWorkerRow, StaffWorkerRow.id == StaffAssignmentRow.worker_id)
            .where(StaffAssignmentRow.id == assignment_id)
        )
        for row, worker_name in rows:
            return _view(row, worker_name)
        return None

    async def _flush(self) -> None:
        """Envía los cambios a PostgreSQL traduciendo el rechazo por solape.

        La aplicación consulta solapes antes de guardar para dar un 409 con detalle;
        esto cubre la carrera en que dos transacciones pasan esa comprobación y la
        restricción de exclusión decide. Se inspecciona el SQLSTATE y el nombre de la
        restricción del error de asyncpg, sin depender del texto del mensaje.
        """
        try:
            await self._session.flush()
        except IntegrityError as error:
            if _is_no_overlap_violation(error):
                raise AssignmentOverlapError() from error
            raise


def _is_no_overlap_violation(error: IntegrityError) -> bool:
    original = error.orig
    sqlstate = getattr(original, "sqlstate", None)
    constraint = getattr(original, "constraint_name", None)
    return sqlstate == _EXCLUSION_SQLSTATE or constraint == _NO_OVERLAP_CONSTRAINT


def _view(row: StaffAssignmentRow, worker_name: str) -> AssignmentView:
    assignment = row_to_assignment(row)
    return AssignmentView(
        id=assignment.id,
        event_id=assignment.event_id,
        worker_id=assignment.worker_id,
        worker_name=worker_name,
        function=assignment.function,
        function_description=assignment.function_description,
        start_at=assignment.start_at,
        end_at=assignment.end_at,
        pay_cents=assignment.pay.cents,
        currency=assignment.pay.currency,
        status=assignment.status,
    )
