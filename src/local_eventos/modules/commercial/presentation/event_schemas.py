"""Forma de los datos de eventos en la API (HU10)."""

from datetime import date, datetime, time
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventSummary,
)
from local_eventos.modules.commercial.application.events.use_cases.events import EventPage
from local_eventos.modules.commercial.domain.contracts.contract import Contract
from local_eventos.modules.commercial.domain.events.event import Event, EventStatus
from local_eventos.modules.commercial.domain.quotes.quote import EventType, LineKind, LineUnit
from local_eventos.modules.commercial.presentation.contract_schemas import PaymentIn


class EventConvertIn(BaseModel):
    contract_id: UUID
    coordinator_id: UUID | None = Field(
        default=None, description="Responsable de coordinación. Si se omite: quien convierte"
    )


class EventCancelIn(BaseModel):
    reason: str
    refund_cents: int | None = Field(default=None, description="Solo si se devolvió dinero")
    refund: PaymentIn | None = Field(default=None, description="Cómo se devolvió")
    note: str | None = None


class EventCancellationOut(BaseModel):
    reason: str
    refund_cents: int | None = Field(description="Devolución registrada en el contrato")
    note: str | None
    cancelled_at: datetime


class CoordinatorOut(BaseModel):
    id: UUID
    name: str


class EventServiceOut(BaseModel):
    kind: LineKind
    service_id: UUID | None
    description: str
    unit: LineUnit
    quantity: int


class EventOut(BaseModel):
    id: UUID
    code: str
    contract_id: UUID
    contract_code: str
    quote_id: UUID
    quote_code: str
    client_id: UUID
    client_name: str
    event_type: EventType
    event_date: date
    start_time: time
    end_time: time
    ends_next_day: bool
    venue: str
    guests: int
    coordinator_id: UUID
    coordinator_name: str | None = Field(description="Vacío si el usuario ya no está activo")
    status: EventStatus
    services: list[EventServiceOut]
    cancellation: EventCancellationOut | None
    created_at: datetime

    @classmethod
    def from_event(
        cls,
        event: Event,
        *,
        contract: Contract | None,
        quote_code: str,
        client_name: str,
        coordinator_name: str | None,
    ) -> Self:
        return cls(
            id=event.id,
            code=event.code,
            contract_id=event.contract_id,
            contract_code=contract.code if contract else "",
            quote_id=event.quote_id,
            quote_code=quote_code,
            client_id=event.client_id,
            client_name=client_name,
            event_type=event.event_type,
            event_date=event.event_date,
            start_time=event.start_time,
            end_time=event.end_time,
            ends_next_day=event.ends_next_day,
            venue=event.venue,
            guests=event.guests,
            coordinator_id=event.coordinator_id,
            coordinator_name=coordinator_name,
            status=event.status,
            services=[
                EventServiceOut(
                    kind=s.kind,
                    service_id=s.service_id,
                    description=s.description,
                    unit=s.unit,
                    quantity=s.quantity,
                )
                for s in event.services
            ],
            cancellation=_cancellation(event, contract),
            created_at=event.created_at,
        )


def _cancellation(event: Event, contract: Contract | None) -> EventCancellationOut | None:
    if event.cancellation is None:
        return None
    contract_cancellation = contract.cancellation if contract else None
    return EventCancellationOut(
        reason=event.cancellation.reason,
        refund_cents=contract_cancellation.refund_cents if contract_cancellation else None,
        note=contract_cancellation.note if contract_cancellation else None,
        cancelled_at=event.cancellation.cancelled_at,
    )


class EventSummaryOut(BaseModel):
    id: UUID
    code: str
    contract_id: UUID
    client_name: str
    event_type: EventType
    event_date: date
    start_time: time
    end_time: time
    venue: str
    guests: int
    coordinator_id: UUID
    coordinator_name: str | None
    status: EventStatus

    @classmethod
    def from_summary(cls, summary: EventSummary, coordinator_name: str | None) -> Self:
        return cls(
            id=summary.id,
            code=summary.code,
            contract_id=summary.contract_id,
            client_name=summary.client_name,
            event_type=summary.event_type,
            event_date=summary.event_date,
            start_time=summary.start_time,
            end_time=summary.end_time,
            venue=summary.venue,
            guests=summary.guests,
            coordinator_id=summary.coordinator_id,
            coordinator_name=coordinator_name,
            status=summary.status,
        )


class EventPageOut(BaseModel):
    items: list[EventSummaryOut]
    total: int
    page: int
    page_size: int

    @classmethod
    def from_page(cls, page: EventPage, names: dict[UUID, str]) -> Self:
        return cls(
            items=[
                EventSummaryOut.from_summary(s, names.get(s.coordinator_id)) for s in page.items
            ],
            total=page.total,
            page=page.page,
            page_size=page.page_size,
        )
