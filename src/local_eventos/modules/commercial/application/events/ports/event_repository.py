"""Puerto del repositorio de eventos: la aplicación lo usa, la infraestructura lo cumple."""

from dataclasses import dataclass
from datetime import date, time
from typing import Protocol
from uuid import UUID

from local_eventos.modules.commercial.domain.events.event import Event, EventStatus
from local_eventos.modules.commercial.domain.quotes.quote import EventType


@dataclass(frozen=True)
class EventFilters:
    text: str = ""  # parte del código o del nombre del cliente
    status: EventStatus | None = None
    event_type: EventType | None = None
    date_from: date | None = None
    date_to: date | None = None


@dataclass(frozen=True)
class EventSummary:
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
    status: EventStatus


class EventRepository(Protocol):
    async def get(self, event_id: UUID) -> Event | None: ...

    async def get_by_contract(self, contract_id: UUID) -> Event | None: ...

    async def add(self, event: Event) -> None:
        """Si el contrato ya tiene evento, lanza `EventAlreadyExistsError` (CA-10.5)."""
        ...

    async def update(self, event: Event) -> None: ...

    async def next_number(self, year: int) -> int: ...

    async def search(
        self, filters: EventFilters, *, limit: int, offset: int
    ) -> tuple[list[EventSummary], int]:
        """Una página, de la fecha más próxima a la más lejana, y el total que cumple el filtro."""
        ...
