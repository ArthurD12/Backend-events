"""Puerto para liberar al personal de un evento cancelado (R-STF-5).

Lo cumple `staff.public_api.assignment_releaser` y se conecta en `commercial.presentation`:
así `commercial.application` no importa `staff` y no hay ciclo entre módulos.
"""

from datetime import datetime
from typing import Protocol
from uuid import UUID


class AssignmentReleaser(Protocol):
    async def __call__(self, event_id: UUID, *, released_by: UUID, now: datetime) -> int:
        """Retira las asignaciones vigentes del evento y devuelve cuántas eran."""
        ...
