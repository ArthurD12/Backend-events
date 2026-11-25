"""Casos de uso de actividades y observaciones del evento (HU13)."""

from uuid import UUID

from local_eventos.modules.commercial.application.events.errors import (
    ActivityNotFoundError,
    ActivityResponsibleInvalidError,
    NoteNotAuthorError,
    NoteNotFoundError,
)
from local_eventos.modules.commercial.application.events.ports.event_log_repository import (
    EventLogRepository,
)
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventRepository,
)
from local_eventos.modules.commercial.application.events.use_cases.events import GetEvent
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.domain.events.activity import EventActivity, EventNote
from local_eventos.modules.commercial.domain.events.event import Event
from local_eventos.modules.identity.public_api import CoordinatorLookup


async def _check_responsible(coordinators: CoordinatorLookup, responsible_id: UUID) -> None:
    """R-ACT-4: un usuario activo, administrador o encargado de eventos."""
    if responsible_id not in {c.id for c in await coordinators()}:
        raise ActivityResponsibleInvalidError()


async def _activity_and_event(
    events: EventRepository, log: EventLogRepository, activity_id: UUID
) -> tuple[EventActivity, Event]:
    activity = await log.get_activity(activity_id)
    if activity is None:
        raise ActivityNotFoundError()
    event = await GetEvent(events)(activity.event_id)
    event.check_activities_open()
    return activity, event


class AddActivity:
    def __init__(
        self,
        events: EventRepository,
        log: EventLogRepository,
        coordinators: CoordinatorLookup,
        clock: Clock,
    ) -> None:
        self._events = events
        self._log = log
        self._coordinators = coordinators
        self._clock = clock

    async def __call__(
        self,
        event_id: UUID,
        *,
        description: str,
        created_by: UUID,
        responsible_id: UUID | None = None,
    ) -> EventActivity:
        """CA-13.1. Si no se indica responsable, lo es quien la crea (R-ACT-4)."""
        event = await GetEvent(self._events)(event_id)
        event.check_activities_open()
        activity = EventActivity.create(
            event_id=event.id,
            description=description,
            responsible_id=responsible_id or created_by,
            created_by=created_by,
            now=self._clock.now(),
        )
        await _check_responsible(self._coordinators, activity.responsible_id)
        await self._log.add_activity(activity)
        return activity


class CompleteActivity:
    def __init__(self, events: EventRepository, log: EventLogRepository, clock: Clock) -> None:
        self._events = events
        self._log = log
        self._clock = clock

    async def __call__(self, activity_id: UUID, *, by: UUID) -> EventActivity:
        """CA-13.3: queda quién la completó y cuándo, también en el historial."""
        activity, _ = await _activity_and_event(self._events, self._log, activity_id)
        change = activity.complete(by=by, now=self._clock.now())
        await self._log.update_activity(activity, change)
        return activity


class ReopenActivity:
    def __init__(self, events: EventRepository, log: EventLogRepository, clock: Clock) -> None:
        self._events = events
        self._log = log
        self._clock = clock

    async def __call__(self, activity_id: UUID, *, by: UUID) -> EventActivity:
        """CA-13.3: vuelve a pendiente; el historial guarda quién y cuándo."""
        activity, _ = await _activity_and_event(self._events, self._log, activity_id)
        change = activity.reopen(by=by, now=self._clock.now())
        await self._log.update_activity(activity, change)
        return activity


class ChangeActivityResponsible:
    def __init__(
        self, events: EventRepository, log: EventLogRepository, coordinators: CoordinatorLookup
    ) -> None:
        self._events = events
        self._log = log
        self._coordinators = coordinators

    async def __call__(self, activity_id: UUID, *, responsible_id: UUID) -> EventActivity:
        """R-ACT-4: el responsable se puede cambiar mientras el evento admite actividades."""
        activity, _ = await _activity_and_event(self._events, self._log, activity_id)
        await _check_responsible(self._coordinators, responsible_id)
        activity.change_responsible(responsible_id)
        await self._log.update_activity(activity)
        return activity


class ListActivities:
    def __init__(self, events: EventRepository, log: EventLogRepository) -> None:
        self._events = events
        self._log = log

    async def __call__(self, event_id: UUID) -> list[EventActivity]:
        """CA-13.5 y CA-13.7: por orden de creación; se ven en cualquier estado del evento."""
        event = await GetEvent(self._events)(event_id)
        return await self._log.list_activities(event.id)


class AddNote:
    def __init__(self, events: EventRepository, log: EventLogRepository, clock: Clock) -> None:
        self._events = events
        self._log = log
        self._clock = clock

    async def __call__(self, event_id: UUID, *, text: str, created_by: UUID) -> EventNote:
        """CA-13.4 y R-ACT-2: también con el evento finalizado; nunca si está cancelado."""
        event = await GetEvent(self._events)(event_id)
        event.check_notes_open()
        note = EventNote.create(
            event_id=event.id, text=text, created_by=created_by, now=self._clock.now()
        )
        await self._log.add_note(note)
        return note


class EditNote:
    def __init__(self, events: EventRepository, log: EventLogRepository, clock: Clock) -> None:
        self._events = events
        self._log = log
        self._clock = clock

    async def __call__(
        self, note_id: UUID, *, text: str, editor_id: UUID, is_admin: bool
    ) -> EventNote:
        """R-ACT-1 y R-ACT-6: la edita su autor o un administrador; queda quién y cuándo."""
        note = await self._log.get_note(note_id)
        if note is None:
            raise NoteNotFoundError()
        if not note.can_be_edited_by(editor_id, is_admin=is_admin):
            raise NoteNotAuthorError()
        event = await GetEvent(self._events)(note.event_id)
        event.check_notes_open()
        note.edit(text, by=editor_id, now=self._clock.now())
        await self._log.update_note(note)
        return note


class ListNotes:
    def __init__(self, events: EventRepository, log: EventLogRepository) -> None:
        self._events = events
        self._log = log

    async def __call__(self, event_id: UUID) -> list[EventNote]:
        """CA-13.5: de la más reciente a la más antigua."""
        event = await GetEvent(self._events)(event_id)
        return await self._log.list_notes(event.id)
