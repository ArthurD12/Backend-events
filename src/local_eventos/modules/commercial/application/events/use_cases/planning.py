"""Casos de uso de planificación y estado del evento (HU11).

Cada cambio deja su fila en el historial (CA-11.5). "Hoy" es la fecha de Lima del reloj.
"""

from dataclasses import dataclass
from datetime import date, time
from uuid import UUID

from local_eventos.modules.commercial.application.events.errors import (
    EventCoordinatorInvalidError,
)
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventRepository,
)
from local_eventos.modules.commercial.application.events.ports.reservation_releaser import (
    ReservationReleaser,
)
from local_eventos.modules.commercial.application.events.use_cases.events import GetEvent
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.domain.events.event import (
    Event,
    EventChange,
    PlanningWarning,
)
from local_eventos.modules.identity.public_api import CoordinatorLookup


@dataclass(frozen=True)
class EventPlanning:
    event_date: date
    start_time: time
    end_time: time
    venue: str
    guests: int
    coordinator_id: UUID


@dataclass(frozen=True)
class PlanningResult:
    event: Event
    warnings: tuple[PlanningWarning, ...]


class UpdateEventPlanning:
    def __init__(
        self, events: EventRepository, coordinators: CoordinatorLookup, clock: Clock
    ) -> None:
        self._events = events
        self._coordinators = coordinators
        self._clock = clock

    async def __call__(
        self, event_id: UUID, planning: EventPlanning, *, by: UUID
    ) -> PlanningResult:
        """CA-11.2, R-EVT-6, R-EVT-7 y R-EVT-9. Sin cambios, no se escribe en el historial."""
        event = await GetEvent(self._events)(event_id)
        change = event.update_planning(
            event_date=planning.event_date,
            start_time=planning.start_time,
            end_time=planning.end_time,
            venue=planning.venue,
            guests=planning.guests,
            coordinator_id=planning.coordinator_id,
            by=by,
            now=self._clock.now(),
            today=self._clock.today(),
        )
        # RN09: también si no cambia, el responsable debe seguir siendo válido.
        if planning.coordinator_id not in {c.id for c in await self._coordinators()}:
            raise EventCoordinatorInvalidError()
        if change is None:
            return PlanningResult(event, ())
        await self._events.update(event, change)
        return PlanningResult(event, change.warnings)


class ConfirmEvent:
    def __init__(self, events: EventRepository, clock: Clock) -> None:
        self._events = events
        self._clock = clock

    async def __call__(self, event_id: UUID, *, by: UUID) -> Event:
        """CA-11.4: programado → confirmado."""
        event = await GetEvent(self._events)(event_id)
        await self._events.update(event, event.confirm(by=by, now=self._clock.now()))
        return event


class StartEvent:
    def __init__(self, events: EventRepository, clock: Clock) -> None:
        self._events = events
        self._clock = clock

    async def __call__(self, event_id: UUID, *, by: UUID) -> Event:
        """CA-11.4 y R-EVT-8: confirmado → en ejecución, solo el día del evento (en Lima)."""
        event = await GetEvent(self._events)(event_id)
        change = event.start(by=by, now=self._clock.now(), today=self._clock.today())
        await self._events.update(event, change)
        return event


class FinishEvent:
    def __init__(
        self, events: EventRepository, clock: Clock, reservations: ReservationReleaser
    ) -> None:
        self._events = events
        self._clock = clock
        self._reservations = reservations

    async def __call__(self, event_id: UUID, *, by: UUID) -> Event:
        """CA-11.4 y R-EVT-8: en ejecución → finalizado; no exige saldo en cero."""
        event = await GetEvent(self._events)(event_id)
        await self._events.update(event, event.finish(by=by, now=self._clock.now()))
        await self._reservations(event.id)  # R-REC-3: lo reservado vuelve a estar disponible
        return event


class ListEventChanges:
    def __init__(self, events: EventRepository) -> None:
        self._events = events

    async def __call__(self, event_id: UUID) -> list[EventChange]:
        """CA-11.5: del cambio más antiguo al más reciente; se ve en cualquier estado."""
        event = await GetEvent(self._events)(event_id)
        return await self._events.list_changes(event.id)
