"""Tablas de inventario (prefijo `inventory_`).

`inventory_movements` es de solo inserción: un trigger de la migración rechaza UPDATE y DELETE.
`inventory_stock` guarda la suma de los movimientos de cada producto y nunca baja de cero.
Evento, proveedor, compra y usuario son IDs de otros módulos: sin FK (AGENTS.md, regla 3).
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from local_eventos.shared.infrastructure.orm import Base

QUANTITY = Numeric(12, 3)


class ProductRow(Base):
    __tablename__ = "inventory_products"
    __table_args__ = (
        CheckConstraint(
            "category IN ('SUPPLIES', 'BEVERAGES', 'DINNERWARE', 'GLASSWARE', 'CUTLERY',"
            " 'LINENS', 'FURNITURE', 'DISPOSABLES', 'CLEANING', 'OTHER')",
            name="category_valid",
        ),
        CheckConstraint(
            "unit IN ('UNIT', 'KG', 'G', 'LITER', 'ML', 'DOZEN', 'PACKAGE', 'BOX')",
            name="unit_valid",
        ),
        CheckConstraint("kind IN ('CONSUMABLE', 'REUSABLE')", name="kind_valid"),
        CheckConstraint("min_stock >= 0", name="min_stock_not_negative"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(15))
    unit: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(12))
    min_stock: Mapped[Decimal] = mapped_column(QUANTITY)
    active: Mapped[bool]


class MovementRow(Base):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('ENTRY', 'EXIT', 'RETURN', 'WASTE', 'ADJUSTMENT')", name="kind_valid"
        ),
        CheckConstraint(
            "(kind = 'ADJUSTMENT' AND quantity <> 0) OR (kind <> 'ADJUSTMENT' AND quantity > 0)",
            name="quantity_sign",
        ),
        CheckConstraint(
            "kind NOT IN ('EXIT', 'RETURN') OR event_id IS NOT NULL", name="event_required"
        ),
        CheckConstraint(
            "kind NOT IN ('ENTRY', 'ADJUSTMENT') OR event_id IS NULL", name="event_not_allowed"
        ),
        CheckConstraint(
            "(kind = 'ENTRY') = (unit_cost_cents IS NOT NULL) AND (unit_cost_cents >= 0"
            " OR unit_cost_cents IS NULL)",
            name="entry_cost",
        ),
        CheckConstraint(
            "kind = 'ENTRY' OR (supplier_id IS NULL AND lot IS NULL AND expires_on IS NULL"
            " AND purchase_id IS NULL)",
            name="entry_only_fields",
        ),
        CheckConstraint(
            "kind NOT IN ('WASTE', 'ADJUSTMENT') OR reason IS NOT NULL", name="reason_required"
        ),
        Index("ix_inventory_movements_product_recorded", "product_id", "recorded_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("inventory_products.id"))
    kind: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[Decimal] = mapped_column(QUANTITY)
    occurred_on: Mapped[date] = mapped_column(Date)
    event_id: Mapped[UUID | None] = mapped_column(index=True)
    unit_cost_cents: Mapped[int | None]
    supplier_id: Mapped[UUID | None]
    lot: Mapped[str | None] = mapped_column(String(50))
    expires_on: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(500))
    purchase_id: Mapped[UUID | None] = mapped_column(index=True)
    recorded_by: Mapped[UUID]
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StockRow(Base):
    __tablename__ = "inventory_stock"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="quantity_not_negative"),
        CheckConstraint("avg_cost_cents >= 0", name="avg_cost_not_negative"),
    )

    product_id: Mapped[UUID] = mapped_column(ForeignKey("inventory_products.id"), primary_key=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY)
    avg_cost_cents: Mapped[int]
