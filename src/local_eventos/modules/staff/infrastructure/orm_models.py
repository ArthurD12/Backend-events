"""Tablas del personal en PostgreSQL (HU15). Prefijo `staff_` por ser de este módulo.

Estas clases describen las tablas, no son las entidades del dominio: `mappers.py`
traduce entre `Worker`/`WorkerAudit` y sus filas. La auditoría es append-only y su
trigger lo crea la migración (T-10), igual que `identity_access_log` y `ledger_payments`.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
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


class StaffWorkerRow(Base):
    """Ficha del trabajador. La baja es lógica (`status`), nunca borrado físico (R-STF-2)."""

    __tablename__ = "staff_workers"
    __table_args__ = (
        # El documento no se repite aunque dos altas pasen la comprobación de la aplicación.
        UniqueConstraint(
            "document_type", "document_number", name="uq_staff_workers_document"
        ),
        CheckConstraint("btrim(name) <> ''", name="name_not_empty"),
        CheckConstraint(_DOCUMENT_VALID, name="document_valid"),
        CheckConstraint(
            "phone IS NULL OR phone ~ '^[0-9]+$'", name="phone_digits"
        ),
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
    status: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'ACTIVE'")
    )
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
    worker_id: Mapped[UUID] = mapped_column(
        ForeignKey("staff_workers.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(12))
    reason: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[UUID]  # usuario de identity: sin FK entre módulos (regla 3)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


Index(
    "ix_staff_worker_audit_worker_changed",
    StaffWorkerAuditRow.worker_id,
    StaffWorkerAuditRow.changed_at,
)
