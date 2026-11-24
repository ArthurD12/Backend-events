"""Eventos y responsables en memoria para probar sin base de datos."""

from dataclasses import replace
from uuid import UUID

from local_eventos.modules.commercial.application.clients.search_text import normalize
from local_eventos.modules.commercial.application.events.errors import EventAlreadyExistsError
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventFilters,
    EventSummary,
)
from local_eventos.modules.commercial.domain.events.event import Event
from local_eventos.modules.identity.public_api import Coordinator


class InMemoryEventRepository:
    def __init__(self, client_names: dict[UUID, str] | None = None) -> None:
        self.events: dict[UUID, Event] = {}
        self.counters: dict[int, int] = {}
        self._client_names = client_names or {}

    async def get(self, event_id: UUID) -> Event | None:
        event = self.events.get(event_id)
        return replace(event) if event else None

    async def get_by_contract(self, contract_id: UUID) -> Event | None:
        return next(
            (replace(e) for e in self.events.values() if e.contract_id == contract_id), None
        )

    async def add(self, event: Event) -> None:
        if any(e.contract_id == event.contract_id for e in self.events.values()):
            raise EventAlreadyExistsError()
        self.events[event.id] = replace(event)

    async def update(self, event: Event) -> None:
        self.events[event.id] = replace(event)

    async def next_number(self, year: int) -> int:
        self.counters[year] = self.counters.get(year, 0) + 1
        return self.counters[year]

    async def search(
        self, filters: EventFilters, *, limit: int, offset: int
    ) -> tuple[list[EventSummary], int]:
        text = normalize(filters.text)
        found = [
            EventSummary(
                id=e.id,
                code=e.code,
                contract_id=e.contract_id,
                client_name=self._client_names.get(e.client_id, ""),
                event_type=e.event_type,
                event_date=e.event_date,
                start_time=e.start_time,
                end_time=e.end_time,
                venue=e.venue,
                guests=e.guests,
                coordinator_id=e.coordinator_id,
                status=e.status,
            )
            for e in sorted(self.events.values(), key=lambda e: (e.event_date, e.start_time))
        ]
        found = [
            s
            for s in found
            if (not text or text in s.code.lower() or text in normalize(s.client_name))
            and (filters.status is None or s.status is filters.status)
            and (filters.event_type is None or s.event_type is filters.event_type)
            and (filters.date_from is None or s.event_date >= filters.date_from)
            and (filters.date_to is None or s.event_date <= filters.date_to)
        ]
        return found[offset : offset + limit], len(found)


class FakeCoordinators:
    def __init__(self, *coordinators: Coordinator) -> None:
        self.coordinators = list(coordinators)

    async def __call__(self) -> list[Coordinator]:
        return list(self.coordinators)
