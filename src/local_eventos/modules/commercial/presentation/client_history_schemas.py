"""Forma del historial del cliente en la API (HU05)."""

from datetime import date
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.commercial.application.clients.use_cases.client_history import (
    History,
    HistoryEvent,
)
from local_eventos.modules.commercial.domain.events.event import EventStatus
from local_eventos.modules.commercial.domain.quotes.quote import EventType
from local_eventos.modules.commercial.presentation.client_schemas import ClientOut
from local_eventos.modules.commercial.presentation.quote_schemas import QuoteSummaryOut


class HistoryEventOut(BaseModel):
    id: UUID
    code: str
    event_type: EventType
    event_date: date
    total_cents: int = Field(description="Total del contrato del evento")
    status: EventStatus

    @classmethod
    def from_event(cls, event: HistoryEvent) -> Self:
        return cls(
            id=event.id,
            code=event.code,
            event_type=event.event_type,
            event_date=event.event_date,
            total_cents=event.total_cents,
            status=event.status,
        )


class HistorySummaryOut(BaseModel):
    quotes: int
    accepted_quotes: int
    events: int
    contracted_cents: int = Field(description="Suma de contratos firmados; sin los anulados")


class ClientHistoryOut(BaseModel):
    client: ClientOut
    summary: HistorySummaryOut
    quotes: list[QuoteSummaryOut] = Field(description="De la fecha de evento más reciente")
    events: list[HistoryEventOut] = Field(description="De la fecha de evento más reciente")

    @classmethod
    def from_history(cls, history: History) -> Self:
        summary = history.summary
        return cls(
            client=ClientOut.from_client(history.client),
            summary=HistorySummaryOut(
                quotes=summary.quotes,
                accepted_quotes=summary.accepted_quotes,
                events=summary.events,
                contracted_cents=summary.contracted_cents,
            ),
            quotes=[QuoteSummaryOut.from_summary(q) for q in history.quotes],
            events=[HistoryEventOut.from_event(e) for e in history.events],
        )
