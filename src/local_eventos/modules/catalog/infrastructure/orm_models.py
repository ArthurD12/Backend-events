"""Tablas del catálogo en PostgreSQL (HU06).

Estas clases describen las tablas, no son las entidades `Category` y `Service` del dominio:
el repositorio traduce entre unas y otras. Prefijo `catalog_` por ser del módulo catálogo.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from local_eventos.shared.infrastructure.orm import Base


class CategoryRow(Base):
    __tablename__ = "catalog_categories"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    active: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# El nombre no se repite sin importar mayúsculas: "Bebidas" y "bebidas" son la misma.
Index("uq_catalog_categories_name_lower", func.lower(CategoryRow.name), unique=True)


class ServiceRow(Base):
    __tablename__ = "catalog_services"
    __table_args__ = (
        CheckConstraint("price_unit IN ('PER_PERSON', 'PER_UNIT')", name="price_unit_valid"),
        CheckConstraint("reference_price_cents >= 0", name="price_not_negative"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    # Misma tabla del módulo: aquí sí va la llave foránea (entre módulos, nunca).
    category_id: Mapped[UUID] = mapped_column(ForeignKey("catalog_categories.id"), index=True)
    price_unit: Mapped[str] = mapped_column(String(10))
    # Dinero en céntimos + moneda (AGENTS.md, regla 4).
    reference_price_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), server_default="PEN")
    description: Mapped[str | None] = mapped_column(String(500))
    active: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
