"""Auditoría de asistencia del personal (HU18, R-ATT-7/R-ATT-22).

Una fila append-only por `RECORDED` o `CORRECTED`. El primer registro no lleva
motivo ni valor anterior; la corrección conserva el valor anterior, el nuevo, el
motivo recortado (1..500), el actor y el instante UTC. El actor es un UUID de
`identity`, sin FK ni import cruzado entre módulos.

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from local_eventos.modules.staff.domain.attendance import AttendanceStatus
from local_eventos.modules.staff.domain.attendance_errors import (
    REASON_MAX_LENGTH,
    AttendanceReasonRequiredError,
    AttendanceStatusInvalidError,
)
from local_eventos.modules.staff.domain.errors import StaffValidationError


class AttendanceAction(StrEnum):
    """Operación auditada sobre la asistencia, de solo inserción (R-ATT-7)."""

    RECORDED = "RECORDED"
    CORRECTED = "CORRECTED"


@dataclass(frozen=True)
class AttendanceAudit:
    """Cambio de asistencia inmutable y de solo inserción (R-ATT-7/R-ATT-22).

    `RECORDED` exige `previous_status=None` y `reason=None`. `CORRECTED` exige un
    valor anterior distinto del nuevo y un motivo recortado de 1..500 caracteres.
    `occurred_at` debe ser timezone-aware y se normaliza a UTC.
    """

    assignment_id: UUID
    action: AttendanceAction
    new_status: AttendanceStatus
    actor_id: UUID
    occurred_at: datetime
    previous_status: AttendanceStatus | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.assignment_id, UUID):
            raise StaffValidationError(
                "staff.audit_invalid", "La asignación auditada debe ser un UUID."
            )
        if not isinstance(self.actor_id, UUID):
            raise StaffValidationError(
                "staff.audit_invalid", "El actor de la auditoría debe ser un UUID."
            )
        if not isinstance(self.action, AttendanceAction):
            raise StaffValidationError(
                "staff.audit_invalid", "La acción de auditoría de asistencia no es válida."
            )
        if (
            not isinstance(self.occurred_at, datetime)
            or self.occurred_at.tzinfo is None
            or self.occurred_at.utcoffset() is None
        ):
            raise StaffValidationError(
                "staff.audit_invalid", "La fecha de la auditoría debe incluir zona horaria."
            )
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(UTC))

        if not isinstance(self.new_status, AttendanceStatus):
            raise AttendanceStatusInvalidError()
        if self.previous_status is not None and not isinstance(
            self.previous_status, AttendanceStatus
        ):
            raise AttendanceStatusInvalidError()

        if self.action is AttendanceAction.RECORDED:
            if self.previous_status is not None:
                raise StaffValidationError(
                    "staff.audit_invalid", "El primer registro no tiene valor anterior."
                )
            if self.reason is not None:
                raise StaffValidationError(
                    "staff.audit_reason_not_allowed",
                    "El primer registro de asistencia no admite motivo.",
                )
            return

        if self.previous_status is None:
            raise StaffValidationError(
                "staff.audit_invalid", "La corrección debe conservar el valor anterior."
            )
        if self.previous_status is self.new_status:
            raise StaffValidationError(
                "staff.audit_invalid", "La corrección debe cambiar el estado de asistencia."
            )
        object.__setattr__(self, "reason", _require_reason(self.reason))

    @classmethod
    def recorded(
        cls,
        *,
        assignment_id: UUID,
        new_status: AttendanceStatus,
        actor_id: UUID,
        occurred_at: datetime,
    ) -> AttendanceAudit:
        """Auditoría del primer registro: sin valor anterior ni motivo (R-ATT-7)."""
        return cls(
            assignment_id=assignment_id,
            action=AttendanceAction.RECORDED,
            new_status=new_status,
            actor_id=actor_id,
            occurred_at=occurred_at,
        )

    @classmethod
    def corrected(
        cls,
        *,
        assignment_id: UUID,
        previous_status: AttendanceStatus,
        new_status: AttendanceStatus,
        reason: str,
        actor_id: UUID,
        occurred_at: datetime,
    ) -> AttendanceAudit:
        """Auditoría de la corrección: valor anterior, nuevo y motivo obligatorio."""
        return cls(
            assignment_id=assignment_id,
            action=AttendanceAction.CORRECTED,
            new_status=new_status,
            actor_id=actor_id,
            occurred_at=occurred_at,
            previous_status=previous_status,
            reason=reason,
        )


def _require_reason(reason: object) -> str:
    if not isinstance(reason, str):
        raise AttendanceReasonRequiredError()
    stripped = reason.strip()
    if not stripped or len(stripped) > REASON_MAX_LENGTH:
        raise AttendanceReasonRequiredError()
    return stripped
