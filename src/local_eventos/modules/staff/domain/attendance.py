"""Agregado `Attendance` de Darze (HU18, R-ATT-1/R-ATT-2/R-ATT-6/R-ATT-17/R-ATT-22).

Una sola asistencia vigente por asignación de HU17: `ATTENDED` ("cumplió") o
`NOT_ATTENDED` ("no cumplió"). "Sin registrar" es ausencia de fila, no un tercer
estado (R-ATT-3). `record` crea el primer registro sin motivo; `correct` cambia el
valor exigiendo motivo y devolviendo la auditoría `CORRECTED`. Repetir el mismo
estado es un no-op idempotente sin auditoría (R-ATT-17); el agregado expone la
comparación con `has_status`.

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from local_eventos.modules.staff.domain.attendance_errors import (
    REASON_MAX_LENGTH,
    AttendanceReasonRequiredError,
    AttendanceStatusInvalidError,
)
from local_eventos.modules.staff.domain.errors import StaffValidationError

if TYPE_CHECKING:
    from local_eventos.modules.staff.domain.attendance_audit import AttendanceAudit


class AttendanceStatus(StrEnum):
    """Estado de asistencia: solo `ATTENDED`/`NOT_ATTENDED` (R-ATT-2)."""

    ATTENDED = "ATTENDED"
    NOT_ATTENDED = "NOT_ATTENDED"


@dataclass
class Attendance:
    """Asistencia vigente de una asignación con actor y `recorded_at` UTC.

    Se construye con `Attendance.record`, que devuelve también la auditoría
    `RECORDED`. `correct` muta el estado y devuelve la auditoría `CORRECTED`, o
    `None` si el estado pedido es el mismo (no-op idempotente).
    """

    assignment_id: UUID
    status: AttendanceStatus
    recorded_by: UUID
    recorded_at: datetime

    def __post_init__(self) -> None:
        _require_uuid(self.assignment_id, "La asignación de la asistencia")
        _require_uuid(self.recorded_by, "El actor del registro de asistencia")
        _require_status(self.status)
        object.__setattr__(self, "recorded_at", _require_aware(self.recorded_at))

    @classmethod
    def record(
        cls,
        *,
        assignment_id: UUID,
        status: AttendanceStatus,
        actor_id: UUID,
        recorded_at: datetime,
    ) -> tuple[Attendance, AttendanceAudit]:
        """Crea el primer registro sin motivo y su auditoría `RECORDED` (R-ATT-7)."""
        from local_eventos.modules.staff.domain.attendance_audit import AttendanceAudit

        new_status = _require_status(status)
        new_assignment_id = _require_uuid(assignment_id, "La asignación de la asistencia")
        new_actor_id = _require_uuid(actor_id, "El actor del registro de asistencia")
        new_recorded_at = _require_aware(recorded_at)

        attendance = cls(
            assignment_id=new_assignment_id,
            status=new_status,
            recorded_by=new_actor_id,
            recorded_at=new_recorded_at,
        )
        audit = AttendanceAudit.recorded(
            assignment_id=new_assignment_id,
            new_status=new_status,
            actor_id=new_actor_id,
            occurred_at=new_recorded_at,
        )
        return attendance, audit

    def has_status(self, status: AttendanceStatus) -> bool:
        """Comparación clara del estado vigente; valida que el valor sea un estado."""
        return _require_status(status) is self.status

    def correct(
        self,
        *,
        new_status: AttendanceStatus,
        reason: str | None,
        actor_id: UUID,
        occurred_at: datetime,
    ) -> AttendanceAudit | None:
        """Corrige el estado con motivo 1..500 y devuelve `CORRECTED` (R-ATT-22).

        Si `new_status` es el estado vigente devuelve `None` sin validar el motivo
        ni escribir auditoría (R-ATT-17). Valida todo antes de mutar: ante un
        error el agregado conserva sus valores anteriores.
        """
        from local_eventos.modules.staff.domain.attendance_audit import AttendanceAudit

        target = _require_status(new_status)
        if target is self.status:
            return None

        clean_reason = _require_reason(reason)
        new_actor_id = _require_uuid(actor_id, "El actor de la corrección de asistencia")
        new_occurred_at = _require_aware(occurred_at)

        audit = AttendanceAudit.corrected(
            assignment_id=self.assignment_id,
            previous_status=self.status,
            new_status=target,
            reason=clean_reason,
            actor_id=new_actor_id,
            occurred_at=new_occurred_at,
        )
        self.status = target
        self.recorded_by = new_actor_id
        self.recorded_at = new_occurred_at
        return audit


def _require_status(value: object) -> AttendanceStatus:
    if not isinstance(value, AttendanceStatus):
        raise AttendanceStatusInvalidError()
    return value


def _require_reason(reason: object) -> str:
    if not isinstance(reason, str):
        raise AttendanceReasonRequiredError()
    stripped = reason.strip()
    if not stripped or len(stripped) > REASON_MAX_LENGTH:
        raise AttendanceReasonRequiredError()
    return stripped


def _require_uuid(value: object, label: str) -> UUID:
    if not isinstance(value, UUID):
        raise StaffValidationError("staff.audit_invalid", f"{label} debe ser un UUID.")
    return value


def _require_aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise StaffValidationError(
            "staff.audit_invalid", "La fecha de la asistencia debe incluir zona horaria."
        )
    return value.astimezone(UTC)
