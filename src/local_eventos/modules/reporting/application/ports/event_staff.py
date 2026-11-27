"""Puerto del personal asignado a un evento (HU14, CA-14.3; depende de HU17).

El adaptador (`infrastructure/event_staff.py`) usa `staff.public_api.event_assignments`, que no
incluye pago. Solo se consulta si el usuario tiene `staff_roster:read` (025).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from local_eventos.modules.staff.public_api import WorkerFunction


@dataclass(frozen=True)
class StaffAssignment:
    worker_id: UUID
    worker_name: str
    role: str  # función en el evento, legible
    function: WorkerFunction
    function_description: str | None
    starts_at: datetime
    ends_at: datetime


class EventStaffLookup(Protocol):
    async def __call__(self, event_id: UUID) -> list[StaffAssignment]:
        """Asignaciones vigentes del evento, sin pago."""
        ...
