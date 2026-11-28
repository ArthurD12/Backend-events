"""Tablas de asistencia del personal en PostgreSQL (HU18, R-ATT-1/R-ATT-7/R-ATT-22).

Estas clases describen las tablas, no son las entidades del dominio: `attendance_mappers.py`
traduce entre `Attendance`/`AttendanceAudit` y sus filas. El estado vigente tiene una
sola fila por asignación (la PK es `assignment_id`) y la auditoría es append-only; los
triggers que rechazan `DELETE`/`UPDATE` los crea la migración (T-07), igual que en las
auditorías de HU15/HU16/HU17. `recorded_by`/`actor_id` son usuarios de `identity` sin
FK (AGENTS.md, regla 3).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from local_eventos.shared.infrastructure.orm import Base

_ATTENDANCE_STATUS_VALID = "status IN ('ATTENDED', 'NOT_ATTENDED')"
_ATTENDANCE_AUDIT_PREVIOUS_STATUS_VALID = (
    "previous_status IS NULL OR previous_status IN ('ATTENDED', 'NOT_ATTENDED')"
)
_ATTENDANCE_AUDIT_NEW_STATUS_VALID = "new_status IN ('ATTENDED', 'NOT_ATTENDED')"
# Réplica exacta del CHECK compuesto de R-ATT-7/R-ATT-22 (plan §5.1).
_ATTENDANCE_AUDIT_RULE_VALID = (
    "(action = 'RECORDED' AND previous_status IS NULL AND reason IS NULL)"
    " OR (action = 'CORRECTED' AND previous_status IS NOT NULL"
    " AND previous_status <> new_status AND reason IS NOT NULL"
    " AND btrim(reason) <> '' AND char_length(btrim(reason)) <= 500)"
)


class StaffAttendanceRow(Base):
    """Estado vigente de asistencia: una fila por asignación (R-ATT-1).

    La PK `assignment_id` apunta a `staff_assignments` con `ON DELETE RESTRICT`; la
    asistencia no se elimina, se corrige (append-only en la auditoría). No hay FK a
    `identity`/`commercial`: `recorded_by` es un UUID sin FK entre módulos.
    """

    __tablename__ = "staff_attendance"
    __table_args__ = (CheckConstraint(_ATTENDANCE_STATUS_VALID, name="status_valid"),)

    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("staff_assignments.id", ondelete="RESTRICT"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(12))
    recorded_by: Mapped[UUID]  # usuario de identity: sin FK entre módulos (regla 3)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StaffAttendanceAuditRow(Base):
    """Una fila por `RECORDED`/`CORRECTED`. Solo se inserta (R-ATT-7/R-ATT-22).

    El CHECK compuesto replica las invariantes del dominio: el primer registro no
    lleva valor anterior ni motivo; la corrección exige valor anterior distinto, motivo
    recortado de 1..500 caracteres. La migración (T-07) añade el trigger append-only.
    """

    __tablename__ = "staff_attendance_audit"
    __table_args__ = (
        CheckConstraint("action IN ('RECORDED', 'CORRECTED')", name="action_valid"),
        CheckConstraint(_ATTENDANCE_AUDIT_PREVIOUS_STATUS_VALID, name="previous_status_valid"),
        CheckConstraint(_ATTENDANCE_AUDIT_NEW_STATUS_VALID, name="new_status_valid"),
        CheckConstraint(_ATTENDANCE_AUDIT_RULE_VALID, name="reason_and_status_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("staff_assignments.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(9))
    previous_status: Mapped[str | None] = mapped_column(String(12))
    new_status: Mapped[str] = mapped_column(String(12))
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[UUID]  # usuario de identity: sin FK entre módulos (regla 3)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


Index(
    "ix_staff_attendance_audit_assignment_occurred",
    StaffAttendanceAuditRow.assignment_id,
    StaffAttendanceAuditRow.occurred_at,
)
