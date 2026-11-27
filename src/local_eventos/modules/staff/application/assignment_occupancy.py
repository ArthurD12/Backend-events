"""Servicio interno de ocupación de trabajadores (HU17, R-ASG-12, plan §2.4).

La base de datos no conoce el estado del evento (no hay FK ni JOIN entre módulos),
así que `staff` libera **perezosamente** las asignaciones de eventos cancelados
antes de la siguiente escritura del trabajador:

1. Lee las asignaciones activas que ocupan (`list_occupying`).
2. Consulta el estado de cada evento por `commercial.public_api.event_lookup`.
3. Si el evento está `CANCELLED`, marca `occupies=false` sin cambiar el estado de
   la asignación ni escribir auditoría: es un dato derivado (CA-17.20).

Si el evento no existe no se libera: no se puede confirmar la cancelación y se
conserva la ocupación. La operación es idempotente y solo persiste una vez.

Python puro: solo stdlib y los puertos de la aplicación (AGENTS.md, regla 2).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from local_eventos.modules.commercial.public_api import EventLookup, EventStatus
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentRepository,
)
from local_eventos.modules.staff.domain.assignment import Assignment


class AssignmentOccupancy:
    """Libera asignaciones de eventos cancelados y detecta asignaciones futuras."""

    def __init__(self, assignments: AssignmentRepository, event_lookup: EventLookup) -> None:
        self._assignments = assignments
        self._event_lookup = event_lookup

    async def release_cancelled(self, worker_id: UUID) -> int:
        """Libera las asignaciones del trabajador cuyo evento está cancelado.

        Devuelve cuántas liberó. Repetir la llamada no libera de nuevo ni vuelve a
        persistir (idempotente). Un evento inexistente no se libera porque no se
        puede confirmar su cancelación.
        """
        released: list[Assignment] = []
        for assignment in await self._assignments.list_occupying(worker_id):
            event = await self._event_lookup(assignment.event_id)
            if event is None or event.status is not EventStatus.CANCELLED:
                continue
            if assignment.release():
                released.append(assignment)

        if released:
            await self._assignments.release(released)
        return len(released)

    async def has_future(self, worker_id: UUID, moment: datetime) -> bool:
        """Indica si el trabajador tiene una asignación activa que termina tras `moment`."""
        return await self._assignments.has_active_ending_after(worker_id, moment)
