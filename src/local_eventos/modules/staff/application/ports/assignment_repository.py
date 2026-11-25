"""Puerto del repositorio de asignaciones. Ninguna se borra: se retiran (CA-17.7)."""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.period import Period


class AssignmentRepository(Protocol):
    async def get(self, assignment_id: UUID) -> Assignment | None: ...

    async def add(self, assignment: Assignment) -> None:
        """Si se cruza con otra vigente del trabajador, lanza `AssignmentOverlapError` (RN12)."""
        ...

    async def update(self, assignment: Assignment) -> None:
        """Solo guarda el retiro."""
        ...

    async def list_for_event(self, event_id: UUID) -> list[Assignment]:
        """Vigentes y retiradas, por hora de inicio."""
        ...

    async def list_active_overlapping(
        self, period: Period, *, worker_id: UUID | None = None
    ) -> list[Assignment]: ...
