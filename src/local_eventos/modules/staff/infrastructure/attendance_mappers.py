"""Mapeo explícito entre el dominio de asistencia y sus filas ORM (HU18).

El dominio no conoce SQLAlchemy (AGENTS.md, regla 2): estas funciones son el único
punto que traduce `Attendance`/`AttendanceAudit` a filas y viceversa. Los enums se
convierten explícitamente y los instantes se normalizan a UTC para que el roundtrip
sea exacto. Sin lógica de negocio: las invariantes viven en el dominio y en el CHECK.
"""

from __future__ import annotations

from datetime import UTC, datetime

from local_eventos.modules.staff.domain.attendance import Attendance, AttendanceStatus
from local_eventos.modules.staff.domain.attendance_audit import AttendanceAction, AttendanceAudit
from local_eventos.modules.staff.infrastructure.attendance_orm_models import (
    StaffAttendanceAuditRow,
    StaffAttendanceRow,
)


def attendance_to_row(attendance: Attendance) -> StaffAttendanceRow:
    """Crea la fila del estado vigente a partir del agregado."""
    return StaffAttendanceRow(
        assignment_id=attendance.assignment_id,
        status=attendance.status.value,
        recorded_by=attendance.recorded_by,
        recorded_at=attendance.recorded_at,
    )


def apply_attendance_to_row(attendance: Attendance, row: StaffAttendanceRow) -> None:
    """Copia el estado vigente a una fila existente (la PK no cambia)."""
    row.status = attendance.status.value
    row.recorded_by = attendance.recorded_by
    row.recorded_at = attendance.recorded_at


def row_to_attendance(row: StaffAttendanceRow) -> Attendance:
    """Reconstruye el agregado desde la fila, con `recorded_at` normalizado a UTC."""
    return Attendance(
        assignment_id=row.assignment_id,
        status=AttendanceStatus(row.status),
        recorded_by=row.recorded_by,
        recorded_at=_as_utc(row.recorded_at),
    )


def attendance_audit_to_row(audit: AttendanceAudit) -> StaffAttendanceAuditRow:
    """Crea la fila de auditoría; nunca se actualiza, solo se inserta."""
    return StaffAttendanceAuditRow(
        assignment_id=audit.assignment_id,
        action=audit.action.value,
        previous_status=None if audit.previous_status is None else audit.previous_status.value,
        new_status=audit.new_status.value,
        reason=audit.reason,
        actor_id=audit.actor_id,
        occurred_at=audit.occurred_at,
    )


def row_to_attendance_audit(row: StaffAttendanceAuditRow) -> AttendanceAudit:
    """Reconstruye la auditoría desde la fila, incluidos los opcionales nulos."""
    return AttendanceAudit(
        assignment_id=row.assignment_id,
        action=AttendanceAction(row.action),
        new_status=AttendanceStatus(row.new_status),
        actor_id=row.actor_id,
        occurred_at=_as_utc(row.occurred_at),
        previous_status=(
            None if row.previous_status is None else AttendanceStatus(row.previous_status)
        ),
        reason=row.reason,
    )


def _as_utc(value: datetime) -> datetime:
    """Normaliza un instante de la fila a UTC; asume UTC si llegara sin zona."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
