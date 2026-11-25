"""Puerto de actividades y observaciones del evento (HU13)."""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.commercial.domain.events.activity import (
    ActivityChange,
    EventActivity,
    EventNote,
)


class EventLogRepository(Protocol):
    async def get_activity(self, activity_id: UUID) -> EventActivity | None: ...

    async def list_activities(self, event_id: UUID) -> list[EventActivity]:
        """Por orden de creación (CA-13.5)."""
        ...

    async def add_activity(self, activity: EventActivity) -> None: ...

    async def update_activity(
        self, activity: EventActivity, change: ActivityChange | None = None
    ) -> None:
        """Guarda la actividad y, si hay `change`, lo agrega al historial (solo inserción)."""
        ...

    async def list_changes(self, activity_id: UUID) -> list[ActivityChange]:
        """Historial de cambios de estado, del más antiguo al más reciente (CA-13.3)."""
        ...

    async def get_note(self, note_id: UUID) -> EventNote | None: ...

    async def list_notes(self, event_id: UUID) -> list[EventNote]:
        """De la más reciente a la más antigua (CA-13.5)."""
        ...

    async def add_note(self, note: EventNote) -> None: ...

    async def update_note(self, note: EventNote) -> None: ...
