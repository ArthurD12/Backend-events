"""Puerto para consultar un evento. Lo cumple `commercial.public_api.event_lookup`.

Se declara aquí, con solo lo que `staff` necesita, para probar los casos de uso sin `commercial`.
"""

from datetime import date, time
from typing import Protocol
from uuid import UUID

ASSIGNABLE_STATUSES = frozenset({"SCHEDULED", "CONFIRMED", "IN_PROGRESS"})  # CA-17.1


class EventInfo(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def code(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def event_date(self) -> date: ...

    @property
    def start_time(self) -> time: ...

    @property
    def end_time(self) -> time: ...


class EventLookup(Protocol):
    async def __call__(self, event_id: UUID) -> EventInfo | None: ...
