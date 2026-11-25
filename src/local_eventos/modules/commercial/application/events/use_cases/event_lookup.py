"""Consulta de un evento para otros módulos (p. ej. inventory valida el evento de una salida).

Solo expone lo que otro módulo necesita saber: código, estado, fecha y horario. Nunca la entidad.
"""

from dataclasses import dataclass
from datetime import date, time
from uuid import UUID

from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventRepository,
)
from local_eventos.modules.commercial.domain.events.event import EventStatus


@dataclass(frozen=True)
class EventInfo:
    id: UUID
    code: str
    status: EventStatus
    event_date: date
    start_time: time
    end_time: time


class LookupEvent:
    def __init__(self, events: EventRepository) -> None:
        self._events = events

    async def __call__(self, event_id: UUID) -> EventInfo | None:
        event = await self._events.get(event_id)
        if event is None:
            return None
        return EventInfo(
            id=event.id,
            code=event.code,
            status=event.status,
            event_date=event.event_date,
            start_time=event.start_time,
            end_time=event.end_time,
        )
