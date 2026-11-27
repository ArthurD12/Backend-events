"""Búsqueda de eventos por código o nombre del cliente, para otros módulos (solo lectura)."""

from dataclasses import dataclass
from datetime import date

from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventFilters,
    EventRepository,
    EventSummary,
)
from local_eventos.modules.commercial.domain.events.event import EventStatus
from local_eventos.modules.commercial.domain.quotes.quote import EventType


class SearchEvents:
    def __init__(self, events: EventRepository) -> None:
        self._events = events

    async def __call__(self, text: str, limit: int = 10) -> list[EventSummary]:
        """Eventos cuyo código o cliente contiene `text`, del más próximo al más lejano."""
        found, _ = await self._events.search(EventFilters(text=text), limit=limit, offset=0)
        return found


@dataclass(frozen=True)
class EventFindResult:
    items: list[EventSummary]
    total: int  # los que cumplen el filtro, aunque `items` se corte en `limit`


class FindEvents:
    """Eventos por fecha, texto (código o cliente), tipo y estado, para el asistente (HU36)."""

    def __init__(self, events: EventRepository) -> None:
        self._events = events

    async def __call__(
        self,
        *,
        text: str = "",
        status: EventStatus | None = None,
        event_type: EventType | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 15,
    ) -> EventFindResult:
        """Del evento más próximo al más lejano."""
        found, total = await self._events.search(
            EventFilters(
                text=" ".join(text.split()),
                status=status,
                event_type=event_type,
                date_from=date_from,
                date_to=date_to,
            ),
            limit=min(max(limit, 1), 100),
            offset=0,
        )
        return EventFindResult(items=found, total=total)
