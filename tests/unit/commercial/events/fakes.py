"""Eventos y responsables en memoria para probar sin base de datos."""

from dataclasses import replace
from uuid import UUID

from local_eventos.modules.commercial.application.clients.search_text import normalize
from local_eventos.modules.commercial.application.events.errors import EventAlreadyExistsError
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventFilters,
    EventSummary,
)
from local_eventos.modules.commercial.domain.events.activity import (
    ActivityChange,
    EventActivity,
    EventNote,
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
            and (filters.client_id is None or self.events[s.id].client_id == filters.client_id)
            and (filters.date_from is None or s.event_date >= filters.date_from)
            and (filters.date_to is None or s.event_date <= filters.date_to)
        ]
        return found[offset : offset + limit], len(found)


class FakeCoordinators:
    def __init__(self, *coordinators: Coordinator) -> None:
        self.coordinators = list(coordinators)

    async def __call__(self) -> list[Coordinator]:
        return list(self.coordinators)


class InMemoryEventLogRepository:
    """Actividades, su historial y observaciones en memoria (HU13)."""

    def __init__(self) -> None:
        self.activities: dict[UUID, EventActivity] = {}
        self.changes: list[ActivityChange] = []
        self.notes: dict[UUID, EventNote] = {}

    async def get_activity(self, activity_id: UUID) -> EventActivity | None:
        activity = self.activities.get(activity_id)
        return replace(activity) if activity else None

    async def list_activities(self, event_id: UUID) -> list[EventActivity]:
        found = [replace(a) for a in self.activities.values() if a.event_id == event_id]
        return sorted(found, key=lambda a: a.created_at)

    async def add_activity(self, activity: EventActivity) -> None:
        self.activities[activity.id] = replace(activity)

    async def update_activity(
        self, activity: EventActivity, change: ActivityChange | None = None
    ) -> None:
        self.activities[activity.id] = replace(activity)
        if change is not None:
            self.changes.append(change)

    async def list_changes(self, activity_id: UUID) -> list[ActivityChange]:
        return [c for c in self.changes if c.activity_id == activity_id]

    async def get_note(self, note_id: UUID) -> EventNote | None:
        note = self.notes.get(note_id)
        return replace(note) if note else None

    async def list_notes(self, event_id: UUID) -> list[EventNote]:
        found = [replace(n) for n in self.notes.values() if n.event_id == event_id]
        return sorted(found, key=lambda n: n.created_at, reverse=True)

    async def add_note(self, note: EventNote) -> None:
        self.notes[note.id] = replace(note)

    async def update_note(self, note: EventNote) -> None:
        self.notes[note.id] = replace(note)
