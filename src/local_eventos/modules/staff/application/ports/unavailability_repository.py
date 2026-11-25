"""Puerto del repositorio de indisponibilidades."""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.staff.domain.period import Period
from local_eventos.modules.staff.domain.unavailability import Unavailability


class UnavailabilityRepository(Protocol):
    async def get(self, unavailability_id: UUID) -> Unavailability | None: ...

    async def add(self, unavailability: Unavailability) -> None: ...

    async def remove(self, unavailability_id: UUID) -> None: ...

    async def list_for_worker(self, worker_id: UUID) -> list[Unavailability]:
        """Del más próximo al más lejano."""
        ...

    async def list_overlapping(
        self, period: Period, *, worker_id: UUID | None = None
    ) -> list[Unavailability]: ...
