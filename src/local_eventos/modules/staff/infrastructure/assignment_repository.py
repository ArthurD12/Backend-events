"""Asignaciones en PostgreSQL (HU17): implementa `AssignmentRepository`.

La restricción de exclusión `ex_staff_assignments_no_overlap` es la garantía final de RN12: si
dos personas asignan a la vez al mismo trabajador en horarios que se cruzan, solo una se guarda.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.staff.application.errors import AssignmentOverlapError
from local_eventos.modules.staff.domain.assignment import (
    Assignment,
    AssignmentStatus,
    AssignmentWithdrawal,
)
from local_eventos.modules.staff.domain.period import Period
from local_eventos.modules.staff.domain.worker import WorkerFunction
from local_eventos.modules.staff.infrastructure.orm_models import NO_OVERLAP, AssignmentRow
from local_eventos.modules.staff.infrastructure.periods import to_period, to_range


class SqlAlchemyAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, assignment_id: UUID) -> Assignment | None:
        row = await self._session.get(AssignmentRow, assignment_id)
        return _to_assignment(row) if row is not None else None

    async def add(self, assignment: Assignment) -> None:
        row = AssignmentRow(
            id=assignment.id,
            worker_id=assignment.worker_id,
            event_id=assignment.event_id,
            event_code=assignment.event_code,
            function=assignment.function.value,
            period=to_range(assignment.period),
            agreed_pay_cents=assignment.agreed_pay_cents,
            created_by=assignment.created_by,
            created_at=assignment.created_at,
        )
        _copy_status(assignment, row)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as error:
            if NO_OVERLAP in str(error.orig):
                raise AssignmentOverlapError() from error
            raise

    async def update(self, assignment: Assignment) -> None:
        row = await self._session.get(AssignmentRow, assignment.id)
        if row is None:
            raise LookupError(f"La asignación {assignment.id} no existe en la base de datos.")
        _copy_status(assignment, row)
        await self._session.flush()

    async def list_for_event(self, event_id: UUID) -> list[Assignment]:
        rows = await self._session.scalars(
            select(AssignmentRow)
            .where(AssignmentRow.event_id == event_id)
            .order_by(AssignmentRow.period, AssignmentRow.created_at)
        )
        return [_to_assignment(row) for row in rows]

    async def list_active_overlapping(
        self, period: Period, *, worker_id: UUID | None = None
    ) -> list[Assignment]:
        query = select(AssignmentRow).where(
            AssignmentRow.status == AssignmentStatus.ACTIVE.value,
            AssignmentRow.period.overlaps(to_range(period)),
        )
        if worker_id is not None:
            query = query.where(AssignmentRow.worker_id == worker_id)
        rows = await self._session.scalars(query.order_by(AssignmentRow.period))
        return [_to_assignment(row) for row in rows]


def _copy_status(assignment: Assignment, row: AssignmentRow) -> None:
    withdrawal = assignment.withdrawal
    row.status = assignment.status.value
    row.withdraw_reason = withdrawal.reason if withdrawal else None
    row.withdrawn_by = withdrawal.withdrawn_by if withdrawal else None
    row.withdrawn_at = withdrawal.withdrawn_at if withdrawal else None


def _to_assignment(row: AssignmentRow) -> Assignment:
    withdrawal = None
    if row.withdrawn_by is not None:
        assert row.withdrawn_at is not None
        withdrawal = AssignmentWithdrawal(
            reason=row.withdraw_reason, withdrawn_by=row.withdrawn_by, withdrawn_at=row.withdrawn_at
        )
    return Assignment(
        id=row.id,
        worker_id=row.worker_id,
        event_id=row.event_id,
        event_code=row.event_code,
        function=WorkerFunction(row.function),
        period=to_period(row.period),
        agreed_pay_cents=row.agreed_pay_cents,
        status=AssignmentStatus(row.status),
        created_by=row.created_by,
        created_at=row.created_at,
        withdrawal=withdrawal,
    )
