"""Tablas del módulo comercial en PostgreSQL: clientes (HU04) y cotizaciones (HU07–HU08).

Estas clases describen las tablas, no son la entidad `Client` del dominio: el repositorio
traduce entre unas y otras. Prefijo `commercial_` por ser del módulo comercial (ADR 0003).
"""

from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from local_eventos.shared.infrastructure.orm import Base


class ClientRow(Base):
    __tablename__ = "commercial_clients"
    __table_args__ = (
        # El documento no se repite, aunque dos personas registren al mismo cliente a la vez.
        UniqueConstraint("document_type", "document_number"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    document_type: Mapped[str] = mapped_column(String(3))
    document_number: Mapped[str] = mapped_column(String(11))
    phone: Mapped[str] = mapped_column(String(16))
    email: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentCorrectionRow(Base):
    """Auditoría de correcciones de documento (RN03). Solo se insertan filas, nunca se editan."""

    __tablename__ = "commercial_client_document_corrections"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("commercial_clients.id"), index=True)
    previous_document_type: Mapped[str] = mapped_column(String(3))
    previous_document_number: Mapped[str] = mapped_column(String(11))
    new_document_type: Mapped[str] = mapped_column(String(3))
    new_document_number: Mapped[str] = mapped_column(String(11))
    reason: Mapped[str] = mapped_column(Text)
    corrected_by: Mapped[UUID]
    corrected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QuoteRow(Base):
    """Cotización (HU07–HU08). Un trigger de la migración impide cambiar su contenido si ya no
    está en borrador; solo puede cambiar el estado (CA-08.4)."""

    __tablename__ = "commercial_quotes"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'SENT', 'ACCEPTED', 'REJECTED')", name="status_valid"),
        CheckConstraint(
            "event_type IN ('WEDDING', 'BIRTHDAY', 'QUINCEANERA', 'CORPORATE', 'GRADUATION',"
            " 'OTHER')",
            name="event_type_valid",
        ),
        CheckConstraint("guests > 0", name="guests_positive"),
        CheckConstraint("total_cents >= 0", name="total_not_negative"),
        CheckConstraint("start_time <> end_time", name="times_differ"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("commercial_clients.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20))
    # Fecha y horario del evento en hora local de Lima: es un plan, no un instante.
    event_date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    venue: Mapped[str] = mapped_column(String(300))
    guests: Mapped[int]
    valid_until: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), index=True)
    total_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), server_default="PEN")
    created_by: Mapped[UUID]  # usuario de identity: sin FK entre módulos (AGENTS.md, regla 3)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class QuoteLineRow(Base):
    """Línea de la cotización con su precio congelado. Solo se cambia mientras está en borrador."""

    __tablename__ = "commercial_quote_lines"
    __table_args__ = (
        CheckConstraint("kind IN ('SERVICE', 'EXTRA')", name="kind_valid"),
        CheckConstraint("price_unit IN ('PER_PERSON', 'PER_UNIT')", name="price_unit_valid"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price_cents >= 0", name="price_not_negative"),
        CheckConstraint("subtotal_cents = quantity * unit_price_cents", name="subtotal_matches"),
        CheckConstraint(
            "(kind = 'SERVICE') = (service_id IS NOT NULL)", name="service_only_in_service"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[UUID] = mapped_column(ForeignKey("commercial_quotes.id"), index=True)
    position: Mapped[int]
    kind: Mapped[str] = mapped_column(String(10))
    service_id: Mapped[UUID | None]  # servicio del catálogo: sin FK entre módulos
    description: Mapped[str] = mapped_column(String(200))
    price_unit: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[int]
    unit_price_cents: Mapped[int]
    catalog_price_cents: Mapped[int | None]
    subtotal_cents: Mapped[int]


class QuoteCounterRow(Base):
    """Último correlativo usado por año, para el código COT-AAAA-NNNN."""

    __tablename__ = "commercial_quote_counters"

    year: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    last: Mapped[int]
