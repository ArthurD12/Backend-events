"""Tabla de pagos (prefijo `ledger_`). Un trigger de la migración impide UPDATE y DELETE."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from local_eventos.shared.infrastructure.orm import Base


class PaymentRow(Base):
    __tablename__ = "ledger_payments"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        CheckConstraint("kind IN ('ADVANCE', 'REFUND')", name="kind_valid"),
        CheckConstraint("method IN ('CASH', 'TRANSFER', 'CARD', 'YAPE_PLIN')", name="method_valid"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    # Contrato de `commercial`: referencia sin FK entre módulos (AGENTS.md, regla 3).
    contract_id: Mapped[UUID] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(10))
    amount_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), server_default="PEN")
    method: Mapped[str] = mapped_column(String(10))
    reference: Mapped[str | None] = mapped_column(String(100))
    paid_on: Mapped[date] = mapped_column(Date)
    recorded_by: Mapped[UUID]
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
