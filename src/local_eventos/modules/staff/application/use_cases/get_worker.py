"""Caso de uso: consultar la ficha completa de un trabajador (HU15, CA-15.7).

Devuelve la ficha con todos sus datos y su estado, también cuando el trabajador
está inactivo: la baja es lógica y la ficha se conserva (R-STF-2). Python puro:
sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from uuid import UUID

from local_eventos.modules.staff.application.errors import WorkerNotFoundError
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerRepository,
)
from local_eventos.modules.staff.domain.worker import Worker

__all__ = ["GetWorker", "WorkerNotFoundError"]


class GetWorker:
    """Recupera la ficha de un trabajador por su identificador."""

    def __init__(self, workers: WorkerRepository) -> None:
        self._workers = workers

    async def execute(self, worker_id: UUID) -> Worker:
        """Devuelve la ficha, activa o inactiva.

        Lanza `WorkerNotFoundError` (`staff.not_found`, 404) si el id no existe.
        """
        worker = await self._workers.get(worker_id)
        if worker is None:
            raise WorkerNotFoundError()
        return worker
