"""Tablas de compras (prefijo `purchasing_`).

`product_id` y `event_id` son IDs de otros módulos: sin FK (AGENTS.md, regla 3). Un trigger de la
migración impide cambiar una compra recibida o cancelada (CA-29.3).
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from local_eventos.shared.infrastructure.orm import Base

QUANTITY = Numeric(12, 3)


class SupplierRow(Base):
    __tablename__ = "purchasing_suppliers"
    __table_args__ = (
        UniqueConstraint("document_type", "document_number"),
        CheckConstraint("document_type IN ('RUC', 'DNI')", name="document_type_valid"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    document_type: Mapped[str] = mapped_column(String(3))
    document_number: Mapped[str] = mapped_column(String(11))
    phone: Mapped[str] = mapped_column(String(16))
    contact_name: Mapped[str | None] = mapped_column(String(300))
    email: Mapped[str | None] = mapped_column(String(300))
    address: Mapped[str | None] = mapped_column(String(300))
    active: Mapped[bool]


class PurchaseCounterRow(Base):
    """Último correlativo COM-AAAA-NNNN de cada año."""

    __tablename__ = "purchasing_purchase_counters"

    year: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    last: Mapped[int]


class PurchaseRow(Base):
    __tablename__ = "purchasing_purchases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('REQUESTED', 'ORDERED', 'RECEIVED', 'CANCELLED')", name="status_valid"
        ),
        CheckConstraint(
            "status <> 'REQUESTED' OR (supplier_id IS NULL AND ordered_at IS NULL)",
            name="requested_has_no_order",
        ),
        CheckConstraint(
            "status NOT IN ('ORDERED', 'RECEIVED') OR (supplier_id IS NOT NULL"
            " AND ordered_at IS NOT NULL)",
            name="ordered_has_supplier",
        ),
        CheckConstraint("(status = 'RECEIVED') = (received_at IS NOT NULL)", name="received_at"),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancel_reason IS NOT NULL)", name="cancelled_has_reason"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    status: Mapped[str] = mapped_column(String(10), index=True)
    event_id: Mapped[UUID | None] = mapped_column(index=True)
    notes: Mapped[str | None] = mapped_column(String(500))
    supplier_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("purchasing_suppliers.id"), index=True
    )
    invoice_number: Mapped[str | None] = mapped_column(String(50))
    created_by: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ordered_by: Mapped[UUID | None]
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_by: Mapped[UUID | None]
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[UUID | None]
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    # Egreso de ledger de esta compra (R-COM-3); único: se registra una sola vez.
    expense_movement_id: Mapped[UUID | None] = mapped_column(unique=True)


class PurchaseLineRow(Base):
    __tablename__ = "purchasing_purchase_lines"
    __table_args__ = (
        UniqueConstraint("purchase_id", "product_id"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_cost_cents >= 0", name="unit_cost_not_negative"),
        CheckConstraint("received_quantity >= 0", name="received_not_negative"),
    )

    purchase_id: Mapped[UUID] = mapped_column(
        ForeignKey("purchasing_purchases.id"), primary_key=True
    )
    position: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    product_id: Mapped[UUID]  # producto de inventory: sin FK entre módulos
    quantity: Mapped[Decimal] = mapped_column(QUANTITY)
    unit_cost_cents: Mapped[int | None]
    received_quantity: Mapped[Decimal | None] = mapped_column(QUANTITY)
    lot: Mapped[str | None] = mapped_column(String(50))
    expires_on: Mapped[date | None] = mapped_column(Date)
