"""Auditoría de operaciones del trabajador (HU15, CA-15.16/CA-15.24, RN03).

Una sola fila por alta, edición, activación o desactivación; sin diff de campos.
Python puro: no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from local_eventos.modules.staff.domain.errors import StaffValidationError

_REASON_ACTIONS = frozenset({"ACTIVATED", "DEACTIVATED"})


class AuditAction(StrEnum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    ACTIVATED = "ACTIVATED"
    DEACTIVATED = "DEACTIVATED"


@dataclass(frozen=True)
class WorkerAudit:
    """Operación auditada sobre un trabajador. Inmutable y de solo inserción.

    `reason` solo se admite en `ACTIVATED`/`DEACTIVATED`; vacío o en blanco se
    normaliza a `None`. `changed_at` debe ser timezone-aware (UTC en la práctica).
    """

    worker_id: UUID
    action: AuditAction
    changed_by: UUID
    changed_at: datetime
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.worker_id, UUID):
            raise StaffValidationError(
                "staff.audit_invalid", "El trabajador auditado debe ser un UUID."
            )
        if not isinstance(self.changed_by, UUID):
            raise StaffValidationError(
                "staff.audit_invalid", "El actor de la auditoría debe ser un UUID."
            )
        if not isinstance(self.action, AuditAction):
            raise StaffValidationError(
                "staff.audit_invalid", "La acción de auditoría no es válida."
            )
        if not isinstance(self.changed_at, datetime) or self.changed_at.tzinfo is None:
            raise StaffValidationError(
                "staff.audit_invalid",
                "La fecha de la auditoría debe incluir zona horaria.",
            )

        if self.reason is not None and not isinstance(self.reason, str):
            raise StaffValidationError(
                "staff.audit_invalid", "El motivo de la auditoría debe ser texto."
            )
        reason = self.reason.strip() if isinstance(self.reason, str) else None
        if not reason:
            reason = None
        if reason is not None and self.action not in _REASON_ACTIONS:
            raise StaffValidationError(
                "staff.audit_reason_not_allowed",
                f"La acción {self.action} no admite motivo.",
            )
        object.__setattr__(self, "reason", reason)
