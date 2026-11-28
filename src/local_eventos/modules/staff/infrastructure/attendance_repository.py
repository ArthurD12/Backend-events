"""Repositorio de asistencia en PostgreSQL (HU18, T-06): implementa `AttendanceRepository`.

Traduce entre `Attendance`/`AttendanceAudit` y sus filas ORM mediante
`attendance_mappers.py`; nunca devuelve filas al exterior. No confirma la transacción:
la gestión la decide quien abre la sesión, para que el estado vigente y su auditoría se
guarden juntas o no se guarde ninguna (plan §5.3).

`lock_assignment` bloquea la fila de `staff_assignments` con `SELECT ... FOR UPDATE`
(no el trabajador) para serializar correcciones simultáneas (plan §5.3). El historial
usa `LEFT JOIN` a la asistencia y devuelve una fila por asignación `ACTIVE`/`CANCELLED`,
incluidas las que todavía no tienen registro (`attendance_status=None`). No hay
`DELETE` ni se tocan disponibilidad o ledger.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.staff.application.ports.attendance_repository import (
    AttendanceAssignmentView,
    AttendanceHistoryRow,
    AttendanceView,
)
from local_eventos.modules.staff.domain.attendance import Attendance
from local_eventos.modules.staff.domain.attendance_audit import AttendanceAudit
from local_eventos.modules.staff.domain.enums import AssignmentStatus
from local_eventos.modules.staff.infrastructure.attendance_mappers import (
    apply_attendance_to_row,
    attendance_audit_to_row,
    attendance_to_row,
    row_to_attendance,
)
from local_eventos.modules.staff.infrastructure.attendance_orm_models import (
    StaffAttendanceRow,
)
from local_eventos.modules.staff.infrastructure.mappers import row_to_assignment
from local_eventos.modules.staff.infrastructure.orm_models import (
    StaffAssignmentRow,
    StaffWorkerRow,
)


class SqlAlchemyAttendanceRepository:
    """Implementación async del puerto sobre la sesión de SQLAlchemy de la petición."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_assignment(self, assignment_id: UUID) -> AttendanceAssignmentView | None:
        row = (
            await self._session.execute(
                select(StaffAssignmentRow, StaffWorkerRow.name)
                .join(StaffWorkerRow, StaffWorkerRow.id == StaffAssignmentRow.worker_id)
                .where(StaffAssignmentRow.id == assignment_id)
                .with_for_update(of=StaffAssignmentRow)
            )
        ).first()
        if row is None:
            return None
        assignment_row, worker_name = row
        return _assignment_view(assignment_row, worker_name)

    async def get(self, assignment_id: UUID) -> AttendanceView | None:
        row = await self._session.get(StaffAttendanceRow, assignment_id)
        if row is None:
            return None
        attendance = row_to_attendance(row)
        return AttendanceView(
            assignment_id=attendance.assignment_id,
            status=attendance.status,
            recorded_by=attendance.recorded_by,
            recorded_at=attendance.recorded_at,
        )

    async def save(self, attendance: Attendance, audit: AttendanceAudit) -> None:
        row = await self._session.get(StaffAttendanceRow, attendance.assignment_id)
        if row is None:
            self._session.add(attendance_to_row(attendance))
        else:
            apply_attendance_to_row(attendance, row)
        # El estado se escribe antes que su auditoría para que la FK resuelva.
        await self._session.flush()
        self._session.add(attendance_audit_to_row(audit))
        await self._session.flush()

    async def list_history(
        self,
        worker_id: UUID,
        event_id: UUID | None = None,
    ) -> list[AttendanceHistoryRow]:
        query = (
            select(StaffAssignmentRow, StaffWorkerRow.name, StaffAttendanceRow)
            .join(StaffWorkerRow, StaffWorkerRow.id == StaffAssignmentRow.worker_id)
            .outerjoin(
                StaffAttendanceRow,
                StaffAttendanceRow.assignment_id == StaffAssignmentRow.id,
            )
            .where(StaffAssignmentRow.worker_id == worker_id)
            .order_by(StaffAssignmentRow.start_at.desc(), StaffAssignmentRow.id.asc())
        )
        if event_id is not None:
            query = query.where(StaffAssignmentRow.event_id == event_id)
        rows = (await self._session.execute(query)).all()
        return [
            _history_row(assignment_row, worker_name, attendance_row)
            for assignment_row, worker_name, attendance_row in rows
        ]


def _assignment_view(
    assignment_row: StaffAssignmentRow, worker_name: str
) -> AttendanceAssignmentView:
    assignment = row_to_assignment(assignment_row)
    return AttendanceAssignmentView(
        assignment_id=assignment.id,
        event_id=assignment.event_id,
        worker_id=assignment.worker_id,
        worker_name=worker_name,
        function=assignment.function,
        function_description=assignment.function_description,
        start_at=assignment.start_at,
        end_at=assignment.end_at,
        pay_cents=assignment.pay.cents,
        currency=assignment.pay.currency,
        assignment_status=assignment.status,
    )


def _history_row(
    assignment_row: StaffAssignmentRow,
    worker_name: str,
    attendance_row: StaffAttendanceRow | None,
) -> AttendanceHistoryRow:
    assignment = row_to_assignment(assignment_row)
    # Una asignación anulada no admite asistencia: aunque se hubiera registrado
    # antes de anularse, el historial muestra `null` (R-ATT-21/CA-18.21).
    attendance = (
        None
        if attendance_row is None or assignment.status is AssignmentStatus.CANCELLED
        else row_to_attendance(attendance_row)
    )
    return AttendanceHistoryRow(
        assignment_id=assignment.id,
        event_id=assignment.event_id,
        worker_id=assignment.worker_id,
        worker_name=worker_name,
        function=assignment.function,
        function_description=assignment.function_description,
        start_at=assignment.start_at,
        end_at=assignment.end_at,
        pay_cents=assignment.pay.cents,
        currency=assignment.pay.currency,
        assignment_status=assignment.status,
        attendance_status=None if attendance is None else attendance.status,
        recorded_at=None if attendance is None else attendance.recorded_at,
        recorded_by=None if attendance is None else attendance.recorded_by,
    )
