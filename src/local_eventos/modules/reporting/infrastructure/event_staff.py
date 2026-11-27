"""Adaptador de `EventStaffLookup` sobre `staff.public_api.event_assignments` (025).

Solo expone nombre, función y horario: la consulta pública de `staff` no incluye pago,
documento, teléfono ni tarifa.
"""

from uuid import UUID

from local_eventos.modules.reporting.application.ports.event_staff import StaffAssignment
from local_eventos.modules.staff.public_api import EventAssignmentLookup, WorkerFunction

_LABELS = {
    WorkerFunction.COOK: "Cocinero",
    WorkerFunction.WAITER: "Mozo",
    WorkerFunction.BARTENDER: "Bartender",
    WorkerFunction.ASSISTANT: "Ayudante",
    WorkerFunction.COORDINATOR: "Coordinador",
}


class AssignmentsEventStaff:
    def __init__(self, assignments: EventAssignmentLookup) -> None:
        self._assignments = assignments

    async def __call__(self, event_id: UUID) -> list[StaffAssignment]:
        return [
            StaffAssignment(
                worker_id=a.worker_id,
                worker_name=a.worker_name,
                role=a.function_description or _LABELS.get(a.function, a.function.value),
                function=a.function,
                function_description=a.function_description,
                starts_at=a.starts_at,
                ends_at=a.ends_at,
            )
            for a in await self._assignments(event_id)
        ]
