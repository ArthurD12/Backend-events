"""Caso de uso: referencia mínima del trabajador para otros módulos (HU15, CA-15.12).

La usa `staff.public_api` para que HU17 rechace inactivos y copie la función con
la que se trabajó. Solo expone id, nombre, función, descripción y estado: nunca
documento, teléfono ni tarifa. Python puro: sin FastAPI, SQLAlchemy ni Pydantic.
"""

from __future__ import annotations

from uuid import UUID

from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerRef,
    WorkerRepository,
)


class GetWorkerRef:
    """Consulta de solo lectura de la referencia pública del trabajador."""

    def __init__(self, workers: WorkerRepository) -> None:
        self._workers = workers

    async def execute(self, worker_id: UUID) -> WorkerRef | None:
        """Devuelve la referencia o `None` si el id no existe."""
        return await self._workers.lookup(worker_id)
