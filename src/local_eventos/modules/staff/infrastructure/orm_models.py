"""Tablas del módulo de personal (prefijo `staff_`).

Los horarios son rangos `tstzrange` `[inicio, fin)` en UTC. Una restricción de exclusión impide
que un trabajador tenga dos asignaciones vigentes que se crucen (RN12, AGENTS.md regla 7); la
extensión `btree_gist` la crea la migración.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSTZRANGE, ExcludeConstraint, Range
from sqlalchemy.orm import Mapped, mapped_column

from local_eventos.shared.infrastructure.orm import Base

_FUNCTIONS = (
    "function IN ('COOK', 'KITCHEN_ASSISTANT', 'WAITER', 'BARTENDER', 'COORDINATOR', 'SETUP',"
    " 'OTHER')"
)
NO_OVERLAP = "ex_staff_assignments_no_overlap"


class WorkerRow(Base):
    __tablename__ = "staff_workers"
    __table_args__ = (
        # El documento no se repite, aunque dos personas registren al mismo trabajador a la vez.
        UniqueConstraint("document_type", "document_number"),
        CheckConstraint("document_type IN ('DNI', 'CE')", name="document_type_valid"),
        CheckConstraint(_FUNCTIONS, name="function_valid"),
        CheckConstraint("worker_type IN ('FIXED', 'EVENTUAL')", name="worker_type_valid"),
        CheckConstraint("reference_rate_cents >= 0", name="rate_not_negative"),
        Index("ix_staff_workers_function_active", "function", "active"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    document_type: Mapped[str] = mapped_column(String(3))
    document_number: Mapped[str] = mapped_column(String(12))
    phone: Mapped[str] = mapped_column(String(9))
    function: Mapped[str] = mapped_column(String(20))
    worker_type: Mapped[str] = mapped_column(String(10))
    reference_rate_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), server_default="PEN")
    active: Mapped[bool]
    created_by: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[UUID]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UnavailabilityRow(Base):
    __tablename__ = "staff_unavailability"
    __table_args__ = (CheckConstraint("NOT isempty(period)", name="period_not_empty"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    worker_id: Mapped[UUID] = mapped_column(ForeignKey("staff_workers.id"), index=True)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE)
    reason: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AssignmentRow(Base):
    __tablename__ = "staff_assignments"
    __table_args__ = (
        CheckConstraint("NOT isempty(period)", name="period_not_empty"),
        CheckConstraint(_FUNCTIONS, name="function_valid"),
        CheckConstraint("agreed_pay_cents >= 0", name="pay_not_negative"),
        CheckConstraint("status IN ('ACTIVE', 'WITHDRAWN')", name="status_valid"),
        # Retirada si y solo si tiene quién y cuándo (CA-17.7).
        CheckConstraint(
            "(status = 'ACTIVE' AND withdrawn_by IS NULL AND withdrawn_at IS NULL"
            " AND withdraw_reason IS NULL)"
            " OR (status = 'WITHDRAWN' AND withdrawn_by IS NOT NULL AND withdrawn_at IS NOT NULL)",
            name="withdrawal_matches_status",
        ),
        # RN12: dos asignaciones vigentes del mismo trabajador no se cruzan.
        ExcludeConstraint(
            ("worker_id", "="),
            ("period", "&&"),
            using="gist",
            where="status = 'ACTIVE'",
            name=NO_OVERLAP,
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    worker_id: Mapped[UUID] = mapped_column(ForeignKey("staff_workers.id"), index=True)
    # Evento de `commercial`: referencia sin FK entre módulos (AGENTS.md, regla 3).
    event_id: Mapped[UUID] = mapped_column(index=True)
    event_code: Mapped[str] = mapped_column(String(20))
    function: Mapped[str] = mapped_column(String(20))
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE)
    agreed_pay_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), server_default="PEN")
    status: Mapped[str] = mapped_column(String(10))
    created_by: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    withdraw_reason: Mapped[str | None] = mapped_column(String(200))
    withdrawn_by: Mapped[UUID | None]
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
