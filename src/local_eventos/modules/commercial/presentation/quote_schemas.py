"""Forma de los datos de cotizaciones en la API (lo que envía y recibe el frontend).

Solo describen la forma: las reglas (fecha no pasada, al menos una línea…) las aplica el
dominio. El total y los subtotales los calcula siempre el servidor.
"""

from datetime import date, datetime, time
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteSummary,
)
from local_eventos.modules.commercial.application.quotes.use_cases.lines import LineInput
from local_eventos.modules.commercial.application.quotes.use_cases.query_quotes import QuotePage
from local_eventos.modules.commercial.application.quotes.use_cases.save_quote import (
    QuoteCommand,
)
from local_eventos.modules.commercial.domain.quotes.quote import (
    CURRENCY,
    EventType,
    LineKind,
    LineUnit,
    Quote,
    QuoteLine,
    QuoteStatus,
)


class QuoteLineIn(BaseModel):
    kind: LineKind = Field(description="SERVICE (del catálogo) o EXTRA (concepto adicional)")
    service_id: UUID | None = Field(default=None, description="Solo en SERVICE")
    description: str | None = Field(default=None, description="Solo en EXTRA")
    quantity: int | None = Field(
        default=None, description="Si se omite: invitados (por persona) o 1 (por unidad)"
    )
    unit_price_cents: int | None = Field(
        default=None, description="Precio acordado. Si se omite en SERVICE: el del catálogo"
    )

    def to_input(self) -> LineInput:
        return LineInput(
            kind=self.kind,
            service_id=self.service_id,
            description=self.description,
            quantity=self.quantity,
            unit_price_cents=self.unit_price_cents,
        )


class QuoteIn(BaseModel):
    client_id: UUID
    event_type: EventType
    event_date: date
    start_time: time
    end_time: time = Field(
        description="Si es menor que start_time, el evento termina al día siguiente"
    )
    venue: str
    guests: int
    lines: list[QuoteLineIn]
    valid_until: date | None = Field(
        default=None, description="Si se omite: 15 días al crear; se mantiene al modificar"
    )
    notes: str | None = None

    def to_command(self) -> QuoteCommand:
        return QuoteCommand(
            client_id=self.client_id,
            event_type=self.event_type,
            event_date=self.event_date,
            start_time=self.start_time,
            end_time=self.end_time,
            venue=self.venue,
            guests=self.guests,
            lines=[line.to_input() for line in self.lines],
            valid_until=self.valid_until,
            notes=self.notes,
        )


class QuoteStatusIn(BaseModel):
    status: Literal[QuoteStatus.DRAFT, QuoteStatus.SENT, QuoteStatus.ACCEPTED, QuoteStatus.REJECTED]


class QuoteLineOut(BaseModel):
    kind: LineKind
    service_id: UUID | None
    description: str
    unit: LineUnit
    quantity: int
    unit_price_cents: int
    catalog_price_cents: int | None
    subtotal_cents: int

    @classmethod
    def from_line(cls, line: QuoteLine) -> Self:
        return cls(
            kind=line.kind,
            service_id=line.service_id,
            description=line.description,
            unit=line.unit,
            quantity=line.quantity,
            unit_price_cents=line.unit_price_cents,
            catalog_price_cents=line.catalog_price_cents,
            subtotal_cents=line.subtotal_cents,
        )


class QuoteOut(BaseModel):
    id: UUID
    code: str
    client_id: UUID
    client_name: str
    event_type: EventType
    event_date: date
    start_time: time
    end_time: time
    ends_next_day: bool
    venue: str
    guests: int
    valid_until: date
    status: QuoteStatus = Field(description="Estado efectivo: incluye EXPIRED si venció")
    lines: list[QuoteLineOut]
    total_cents: int
    currency: str
    notes: str | None
    created_at: datetime

    @classmethod
    def from_quote(cls, quote: Quote, *, client_name: str, today: date) -> Self:
        details = quote.details
        return cls(
            id=quote.id,
            code=quote.code,
            client_id=quote.client_id,
            client_name=client_name,
            event_type=details.event_type,
            event_date=details.event_date,
            start_time=details.start_time,
            end_time=details.end_time,
            ends_next_day=details.ends_next_day,
            venue=details.venue,
            guests=details.guests,
            valid_until=quote.valid_until,
            status=quote.effective_status(today),
            lines=[QuoteLineOut.from_line(line) for line in quote.lines],
            total_cents=quote.total_cents,
            currency=CURRENCY,
            notes=quote.notes,
            created_at=quote.created_at,
        )


class QuoteSummaryOut(BaseModel):
    id: UUID
    code: str
    client_id: UUID
    client_name: str
    event_type: EventType
    event_date: date
    guests: int
    total_cents: int
    status: QuoteStatus
    valid_until: date

    @classmethod
    def from_summary(cls, summary: QuoteSummary) -> Self:
        return cls(
            id=summary.id,
            code=summary.code,
            client_id=summary.client_id,
            client_name=summary.client_name,
            event_type=summary.event_type,
            event_date=summary.event_date,
            guests=summary.guests,
            total_cents=summary.total_cents,
            status=summary.status,
            valid_until=summary.valid_until,
        )


class QuotePageOut(BaseModel):
    items: list[QuoteSummaryOut]
    total: int
    page: int
    page_size: int

    @classmethod
    def from_page(cls, page: QuotePage) -> Self:
        return cls(
            items=[QuoteSummaryOut.from_summary(item) for item in page.items],
            total=page.total,
            page=page.page,
            page_size=page.page_size,
        )
