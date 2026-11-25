"""Tablas del dinero (prefijo `ledger_`). Un trigger de la migración impide UPDATE y DELETE en
pagos, movimientos y sus anulaciones (AGENTS.md, regla 5)."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from local_eventos.shared.infrastructure.orm import Base


class PaymentRow(Base):
    __tablename__ = "ledger_payments"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        CheckConstraint("kind IN ('ADVANCE', 'INSTALLMENT', 'REFUND')", name="kind_valid"),
        CheckConstraint("method IN ('CASH', 'TRANSFER', 'CARD', 'YAPE_PLIN')", name="method_valid"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True)
    # Contrato de `commercial`: referencia sin FK entre módulos (AGENTS.md, regla 3).
    contract_id: Mapped[UUID] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(11))
    amount_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), server_default="PEN")
    method: Mapped[str] = mapped_column(String(10))
    reference: Mapped[str | None] = mapped_column(String(100))
    paid_on: Mapped[date] = mapped_column(Date, index=True)
    recorded_by: Mapped[UUID]
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PaymentCounterRow(Base):
    """Último correlativo usado por año, para el número PAG-AAAA-NNNN."""

    __tablename__ = "ledger_payment_counters"

    year: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    last: Mapped[int]


class PaymentVoidRow(Base):
    """Anulación de un pago (RN17). Un pago tiene a lo sumo una anulación."""

    __tablename__ = "ledger_payment_voids"

    payment_id: Mapped[UUID] = mapped_column(ForeignKey("ledger_payments.id"), primary_key=True)
    reason: Mapped[str] = mapped_column(String(500))
    voided_by: Mapped[UUID]
    voided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MovementRow(Base):
    """Ingreso o egreso que no es pago de un cliente (HU21)."""

    __tablename__ = "ledger_movements"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        CheckConstraint(
            "(type = 'INCOME' AND category = 'OTHER_INCOME') OR (type = 'EXPENSE' AND category IN"
            " ('SUPPLIES', 'STAFF', 'TRANSPORT', 'OTHER_EXPENSE'))",
            name="category_valid",
        ),
        CheckConstraint("method IN ('CASH', 'TRANSFER', 'CARD', 'YAPE_PLIN')", name="method_valid"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(15))
    concept: Mapped[str] = mapped_column(String(200))
    amount_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), server_default="PEN")
    method: Mapped[str] = mapped_column(String(10))
    reference: Mapped[str | None] = mapped_column(String(100))
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    # Evento de `commercial`: referencia sin FK entre módulos (AGENTS.md, regla 3).
    event_id: Mapped[UUID | None] = mapped_column(index=True)
    recorded_by: Mapped[UUID]
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MovementVoidRow(Base):
    """Anulación de un movimiento (RN17). Un movimiento tiene a lo sumo una anulación."""

    __tablename__ = "ledger_movement_voids"

    movement_id: Mapped[UUID] = mapped_column(ForeignKey("ledger_movements.id"), primary_key=True)
    reason: Mapped[str] = mapped_column(String(500))
    voided_by: Mapped[UUID]
    voided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
