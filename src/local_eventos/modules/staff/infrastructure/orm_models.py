"""Tablas del personal en PostgreSQL (HU15, HU16, HU17). Prefijo `staff_` por ser de este módulo.

Estas clases describen las tablas, no son las entidades del dominio: `mappers.py`
traduce entre `Worker`/`WorkerAudit` y sus filas. La auditoría es append-only y su
trigger lo crea la migración (T-10), igual que `identity_access_log` y `ledger_payments`.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from local_eventos.shared.infrastructure.orm import Base

_DOCUMENT_VALID = (
    "(document_type = 'DNI' AND document_number ~ '^[0-9]{8}$')"
    " OR (document_type = 'CE' AND document_number ~ '^[0-9]{9,12}$')"
)
_FUNCTION_DESCRIPTION_VALID = (
    "(worker_function = 'OTHER' AND function_description IS NOT NULL"
    " AND btrim(function_description) <> '')"
    " OR (worker_function IS DISTINCT FROM 'OTHER' AND function_description IS NULL)"
)
_OVERTIME_VALID = (
    "(overtime_applies AND overtime_rate_cents IS NOT NULL AND overtime_rate_cents > 0)"
    " OR (NOT overtime_applies AND overtime_rate_cents IS NULL)"
)
_AUDIT_REASON_VALID = (
    "reason IS NULL OR (action IN ('ACTIVATED', 'DEACTIVATED') AND btrim(reason) <> '')"
)
_ASSIGNMENT_FUNCTION_DESCRIPTION_VALID = (
    "(worker_function = 'OTHER' AND function_description IS NOT NULL"
    " AND btrim(function_description) <> '')"
    " OR (worker_function IS DISTINCT FROM 'OTHER' AND function_description IS NULL)"
)
_ASSIGNMENT_AUDIT_REASON_VALID = (
    "reason IS NULL OR (action IN ('UPDATED', 'CANCELLED') AND btrim(reason) <> '')"
)
_ASSIGNMENT_AUDIT_SNAPSHOTS_VALID = (
    "(action = 'UPDATED') = (previous_values IS NOT NULL AND new_values IS NOT NULL)"
)


_UNAVAILABILITY_DESCRIPTION_VALID = (
    "(kind = 'OTHER' AND description IS NOT NULL AND btrim(description) <> '')"
    " OR (kind IS DISTINCT FROM 'OTHER' AND description IS NULL)"
)
_UNAVAILABILITY_AUDIT_REASON_VALID = (
    "(action = 'CREATED' AND reason IS NULL)"
    " OR (action IN ('UPDATED', 'CANCELLED')"
    " AND reason IS NOT NULL AND btrim(reason) <> '')"
)
_UNAVAILABILITY_AUDIT_SNAPSHOTS_VALID = (
    "(action = 'UPDATED') = (previous_values IS NOT NULL AND new_values IS NOT NULL)"
)


class StaffWorkerRow(Base):
    """Ficha del trabajador. La baja es lógica (`status`), nunca borrado físico (R-STF-2)."""

    __tablename__ = "staff_workers"
    __table_args__ = (
        # El documento no se repite aunque dos altas pasen la comprobación de la aplicación.
        UniqueConstraint("document_type", "document_number", name="uq_staff_workers_document"),
        CheckConstraint("btrim(name) <> ''", name="name_not_empty"),
        CheckConstraint(_DOCUMENT_VALID, name="document_valid"),
        CheckConstraint("phone IS NULL OR phone ~ '^[0-9]+$'", name="phone_digits"),
        CheckConstraint(
            "worker_function IS NULL OR worker_function IN"
            " ('COOK', 'WAITER', 'BARTENDER', 'ASSISTANT', 'COORDINATOR', 'OTHER')",
            name="function_valid",
        ),
        CheckConstraint(_FUNCTION_DESCRIPTION_VALID, name="function_description_valid"),
        CheckConstraint(
            "worker_type IS NULL OR worker_type IN ('FIXED', 'EVENTUAL')",
            name="worker_type_valid",
        ),
        CheckConstraint("rate_cents IS NULL OR rate_cents >= 0", name="rate_not_negative"),
        CheckConstraint(_OVERTIME_VALID, name="overtime_valid"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="status_valid"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    document_type: Mapped[str] = mapped_column(String(3))
    document_number: Mapped[str] = mapped_column(String(12))
    phone: Mapped[str | None] = mapped_column(Text)
    worker_function: Mapped[str | None] = mapped_column(String(15))
    function_description: Mapped[str | None] = mapped_column(Text)
    worker_type: Mapped[str | None] = mapped_column(String(8))
    rate_cents: Mapped[int | None] = mapped_column(Integer)
    overtime_applies: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    overtime_rate_cents: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'ACTIVE'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# `lower(name)` cubre la búsqueda sin mayúsculas; el resto son filtros del listado.
Index("ix_staff_workers_status_function", StaffWorkerRow.status, StaffWorkerRow.worker_function)
Index("ix_staff_workers_function", StaffWorkerRow.worker_function)
Index("ix_staff_workers_document_number", StaffWorkerRow.document_number)
Index("ix_staff_workers_name_lower", func.lower(StaffWorkerRow.name))


class StaffWorkerAuditRow(Base):
    """Una fila por alta, edición, activación o desactivación. Solo se inserta (RN03)."""

    __tablename__ = "staff_worker_audit"
    __table_args__ = (
        CheckConstraint(
            "action IN ('CREATED', 'UPDATED', 'ACTIVATED', 'DEACTIVATED')",
            name="action_valid",
        ),
        CheckConstraint(_AUDIT_REASON_VALID, name="reason_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    worker_id: Mapped[UUID] = mapped_column(ForeignKey("staff_workers.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(12))
    reason: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[UUID]  # usuario de identity: sin FK entre módulos (regla 3)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


Index(
    "ix_staff_worker_audit_worker_changed",
    StaffWorkerAuditRow.worker_id,
    StaffWorkerAuditRow.changed_at,
)


class StaffAssignmentRow(Base):
    """Trabajador asignado a un evento (HU17, R-ASG-1..R-ASG-9).

    El `event_id` es de `commercial` y no lleva FK (regla 3); `worker_id` sí apunta
    a `staff_workers` con `ON DELETE RESTRICT` porque nunca se borra un trabajador.
    La anulación es lógica (`status`) y la liberación de un evento cancelado se
    expresa con `occupies=false` sin cambiar el estado (R-ASG-12).
    """

    __tablename__ = "staff_assignments"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="window_valid"),
        CheckConstraint("pay_cents >= 0", name="pay_not_negative"),
        CheckConstraint("currency = 'PEN'", name="currency_pen"),
        CheckConstraint(
            "worker_function IN"
            " ('COOK', 'WAITER', 'BARTENDER', 'ASSISTANT', 'COORDINATOR', 'OTHER')",
            name="function_valid",
        ),
        CheckConstraint(
            _ASSIGNMENT_FUNCTION_DESCRIPTION_VALID,
            name="function_description_valid",
        ),
        CheckConstraint("status IN ('ACTIVE', 'CANCELLED')", name="status_valid"),
        CheckConstraint(
            "(status = 'CANCELLED' AND NOT occupies) OR (status = 'ACTIVE')",
            name="occupies_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[UUID]  # referencia a commercial: sin FK entre módulos (regla 3)
    worker_id: Mapped[UUID] = mapped_column(ForeignKey("staff_workers.id", ondelete="RESTRICT"))
    worker_function: Mapped[str] = mapped_column(String(15))
    function_description: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pay_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(CHAR(3))
    status: Mapped[str] = mapped_column(String(9))
    occupies: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


Index("ix_staff_assignments_event_start", StaffAssignmentRow.event_id, StaffAssignmentRow.start_at)
Index(
    "ix_staff_assignments_worker_start",
    StaffAssignmentRow.worker_id,
    StaffAssignmentRow.start_at,
)


class StaffAssignmentAuditRow(Base):
    """Una fila por alta, edición o anulación de una asignación. Solo se inserta (R-ASG-9).

    Los snapshots de la edición se guardan como JSONB; la migración (T-14) crea el
    trigger append-only que rechaza UPDATE y DELETE.
    """

    __tablename__ = "staff_assignment_audit"
    __table_args__ = (
        CheckConstraint("action IN ('CREATED', 'UPDATED', 'CANCELLED')", name="action_valid"),
        CheckConstraint(_ASSIGNMENT_AUDIT_REASON_VALID, name="reason_valid"),
        CheckConstraint(_ASSIGNMENT_AUDIT_SNAPSHOTS_VALID, name="snapshots_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("staff_assignments.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(9))
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[UUID]  # usuario de identity: sin FK entre módulos (regla 3)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    previous_values: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))
    new_values: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))


Index(
    "ix_staff_assignment_audit_assignment_occurred",
    StaffAssignmentAuditRow.assignment_id,
    StaffAssignmentAuditRow.occurred_at,
)


class StaffUnavailabilityRow(Base):
    """Ventana en la que un trabajador no puede trabajar (HU16, R-DIS-1..R-DIS-10).

    `worker_id` apunta a `staff_workers` con `ON DELETE RESTRICT` porque nunca se
    borra un trabajador. No hay FK ni UNIQUE adicional: las indisponibilidades
    solapadas están permitidas (son informativas y no bloquean HU17). La anulación
    es lógica (`status`) y no existe borrado físico.
    """

    __tablename__ = "staff_unavailabilities"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="window_valid"),
        CheckConstraint(
            "kind IN ('VACATION', 'LEAVE', 'REST', 'OTHER')",
            name="kind_valid",
        ),
        CheckConstraint(
            _UNAVAILABILITY_DESCRIPTION_VALID,
            name="description_valid",
        ),
        CheckConstraint("status IN ('ACTIVE', 'CANCELLED')", name="status_valid"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    worker_id: Mapped[UUID] = mapped_column(ForeignKey("staff_workers.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(10))
    description: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(9))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


Index(
    "ix_staff_unavailabilities_worker_start",
    StaffUnavailabilityRow.worker_id,
    StaffUnavailabilityRow.start_at,
)
Index(
    "ix_staff_unavailabilities_start_end",
    StaffUnavailabilityRow.start_at,
    StaffUnavailabilityRow.end_at,
)


class StaffUnavailabilityAuditRow(Base):
    """Una fila por alta, edición o anulación de una indisponibilidad. Solo se inserta.

    Los snapshots de la edición se guardan como JSONB; la migración (T-09) crea el
    trigger append-only que rechaza UPDATE y DELETE.
    """

    __tablename__ = "staff_unavailabilities_audit"
    __table_args__ = (
        CheckConstraint("action IN ('CREATED', 'UPDATED', 'CANCELLED')", name="action_valid"),
        CheckConstraint(_UNAVAILABILITY_AUDIT_REASON_VALID, name="reason_valid"),
        CheckConstraint(_UNAVAILABILITY_AUDIT_SNAPSHOTS_VALID, name="snapshots_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    unavailability_id: Mapped[UUID] = mapped_column(
        ForeignKey("staff_unavailabilities.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(9))
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[UUID]  # usuario de identity: sin FK entre módulos (regla 3)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    previous_values: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))
    new_values: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))


Index(
    "ix_staff_unavailabilities_audit_unavailability_occurred",
    StaffUnavailabilityAuditRow.unavailability_id,
    StaffUnavailabilityAuditRow.occurred_at,
)
