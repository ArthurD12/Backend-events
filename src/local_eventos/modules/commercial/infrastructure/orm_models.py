"""Tablas del módulo comercial en PostgreSQL: clientes, cotizaciones, contratos y eventos.

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


class ContractRow(Base):
    """Contrato (HU41–HU42). `quote_id` es único: una cotización, un solo contrato (R-CON-5).

    Un trigger de la migración impide cambiar montos o firma de un contrato firmado o anulado.
    """

    __tablename__ = "commercial_contracts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING_SIGNATURE', 'SIGNED', 'CANCELLED')", name="status_valid"
        ),
        CheckConstraint("advance_cents > 0 AND advance_cents <= total_cents", name="advance_valid"),
        CheckConstraint(
            "(status = 'SIGNED') <= (signed_on IS NOT NULL AND advance_payment_id IS NOT NULL)",
            name="signed_has_signature",
        ),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancel_reason IS NOT NULL)", name="cancelled_has_reason"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    quote_id: Mapped[UUID] = mapped_column(ForeignKey("commercial_quotes.id"), unique=True)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("commercial_clients.id"), index=True)
    event_date: Mapped[date] = mapped_column(Date)
    total_cents: Mapped[int]
    advance_cents: Mapped[int]
    balance_due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), index=True)
    created_by: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signed_on: Mapped[date | None] = mapped_column(Date)
    signer_name: Mapped[str | None] = mapped_column(String(120))
    advance_payment_id: Mapped[UUID | None]  # pago de `ledger`: sin FK entre módulos
    signature_recorded_by: Mapped[UUID | None]
    signature_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    refund_cents: Mapped[int | None]
    refund_payment_id: Mapped[UUID | None]
    cancel_note: Mapped[str | None] = mapped_column(String(500))
    cancelled_by: Mapped[UUID | None]
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContractCounterRow(Base):
    """Último correlativo usado por año, para el código CON-AAAA-NNNN."""

    __tablename__ = "commercial_contract_counters"

    year: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    last: Mapped[int]


class EventRow(Base):
    """Evento (HU10). `contract_id` es único: un contrato, un solo evento (CA-10.5)."""

    __tablename__ = "commercial_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('SCHEDULED', 'CONFIRMED', 'IN_PROGRESS', 'FINISHED', 'CANCELLED')",
            name="status_valid",
        ),
        CheckConstraint(
            "event_type IN ('WEDDING', 'BIRTHDAY', 'QUINCEANERA', 'CORPORATE', 'GRADUATION',"
            " 'OTHER')",
            name="event_type_valid",
        ),
        CheckConstraint("guests > 0", name="guests_positive"),
        CheckConstraint("start_time <> end_time", name="times_differ"),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancel_reason IS NOT NULL)", name="cancelled_has_reason"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    contract_id: Mapped[UUID] = mapped_column(ForeignKey("commercial_contracts.id"), unique=True)
    quote_id: Mapped[UUID] = mapped_column(ForeignKey("commercial_quotes.id"))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("commercial_clients.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20))
    event_date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    venue: Mapped[str] = mapped_column(String(300))
    guests: Mapped[int]
    coordinator_id: Mapped[UUID]  # usuario de identity: sin FK entre módulos
    status: Mapped[str] = mapped_column(String(15), index=True)
    created_by: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    cancelled_by: Mapped[UUID | None]
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EventServiceRow(Base):
    """Servicio contratado, copiado al evento (CA-10.2)."""

    __tablename__ = "commercial_event_services"
    __table_args__ = (
        CheckConstraint("kind IN ('SERVICE', 'EXTRA')", name="kind_valid"),
        CheckConstraint("price_unit IN ('PER_PERSON', 'PER_UNIT')", name="price_unit_valid"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("commercial_events.id"), index=True)
    position: Mapped[int]
    kind: Mapped[str] = mapped_column(String(10))
    service_id: Mapped[UUID | None]  # servicio del catálogo: sin FK entre módulos
    description: Mapped[str] = mapped_column(String(200))
    price_unit: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[int]


class EventCounterRow(Base):
    """Último correlativo usado por año, para el código EVT-AAAA-NNNN."""

    __tablename__ = "commercial_event_counters"

    year: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    last: Mapped[int]
