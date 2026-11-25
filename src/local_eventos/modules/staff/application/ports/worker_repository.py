"""Puerto del repositorio de trabajadores."""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from local_eventos.modules.staff.domain.worker import (
    Worker,
    WorkerDocument,
    WorkerFunction,
    WorkerType,
)


@dataclass(frozen=True)
class WorkerFilters:
    text: str = ""  # parte del nombre (sin tildes) o del documento
    function: WorkerFunction | None = None
    worker_type: WorkerType | None = None
    active: bool | None = None


class WorkerRepository(Protocol):
    async def get(self, worker_id: UUID) -> Worker | None: ...

    async def get_many(self, worker_ids: Collection[UUID]) -> list[Worker]: ...

    async def get_by_document(self, document: WorkerDocument) -> Worker | None: ...

    async def add(self, worker: Worker) -> None:
        """Si el documento ya es de otro, lanza `DocumentTakenError` (CA-15.2)."""
        ...

    async def update(self, worker: Worker) -> None:
        """Si el documento ya es de otro, lanza `DocumentTakenError` (CA-15.3)."""
        ...

    async def search(self, filters: WorkerFilters) -> list[Worker]:
        """Todos los que cumplen el filtro, por nombre."""
        ...
