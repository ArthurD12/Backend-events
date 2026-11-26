"""Búsqueda de eventos por código o nombre del cliente, para otros módulos (solo lectura)."""

from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventFilters,
    EventRepository,
    EventSummary,
)


class SearchEvents:
    def __init__(self, events: EventRepository) -> None:
        self._events = events

    async def __call__(self, text: str, limit: int = 10) -> list[EventSummary]:
        """Eventos cuyo código o cliente contiene `text`, del más próximo al más lejano."""
        found, _ = await self._events.search(EventFilters(text=text), limit=limit, offset=0)
        return found
