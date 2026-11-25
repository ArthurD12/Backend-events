"""Puerto del personal asignado a un evento (HU14, CA-14.3; depende de HU17).

`staff` aún no publica sus asignaciones: mientras tanto, el adaptador devuelve `None` y la
ficha muestra "Sin información de personal". Cuando `staff.public_api` las exponga, solo cambia
el adaptador de `infrastructure`.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class StaffAssignment:
    worker_id: UUID
    worker_name: str
    role: str  # función en el evento
    starts_at: datetime
    ends_at: datetime


class EventStaffLookup(Protocol):
    async def __call__(self, event_id: UUID) -> list[StaffAssignment] | None:
        """Asignaciones del evento, o `None` si el módulo de personal no las expone aún."""
        ...
