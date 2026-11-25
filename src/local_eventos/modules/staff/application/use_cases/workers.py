"""Casos de uso del registro de personal (HU15)."""

from dataclasses import replace
from uuid import UUID

from local_eventos.modules.staff.application.errors import DocumentTakenError, WorkerNotFoundError
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerFilters,
    WorkerRepository,
)
from local_eventos.modules.staff.domain.worker import Worker, WorkerData


class RegisterWorker:
    def __init__(self, workers: WorkerRepository, clock: Clock) -> None:
        self._workers = workers
        self._clock = clock

    async def __call__(self, data: WorkerData, *, created_by: UUID) -> Worker:
        """CA-15.1 y CA-15.2."""
        worker = Worker.register(data, created_by=created_by, now=self._clock.now())
        if await self._workers.get_by_document(worker.document) is not None:
            raise DocumentTakenError()
        await self._workers.add(worker)
        return worker


class GetWorker:
    def __init__(self, workers: WorkerRepository) -> None:
        self._workers = workers

    async def __call__(self, worker_id: UUID) -> Worker:
        worker = await self._workers.get(worker_id)
        if worker is None:
            raise WorkerNotFoundError()
        return worker


class UpdateWorker:
    def __init__(self, workers: WorkerRepository, clock: Clock) -> None:
        self._workers = workers
        self._clock = clock

    async def __call__(self, worker_id: UUID, data: WorkerData, *, updated_by: UUID) -> Worker:
        """CA-15.3: todos los datos; el documento solo si no lo tiene otro trabajador."""
        worker = await GetWorker(self._workers)(worker_id)
        worker.update(data, updated_by=updated_by, now=self._clock.now())
        owner = await self._workers.get_by_document(worker.document)
        if owner is not None and owner.id != worker.id:
            raise DocumentTakenError()
        await self._workers.update(worker)
        return worker


class SetWorkerActive:
    def __init__(self, workers: WorkerRepository, clock: Clock) -> None:
        self._workers = workers
        self._clock = clock

    async def __call__(self, worker_id: UUID, active: bool, *, updated_by: UUID) -> Worker:
        """CA-15.4 y CA-15.5: no se elimina; sus asignaciones pasadas se conservan."""
        worker = await GetWorker(self._workers)(worker_id)
        worker.set_active(active, updated_by=updated_by, now=self._clock.now())
        await self._workers.update(worker)
        return worker


class ListWorkers:
    def __init__(self, workers: WorkerRepository) -> None:
        self._workers = workers

    async def __call__(self, filters: WorkerFilters) -> list[Worker]:
        """CA-15.6: por función, tipo, estado y texto (nombre sin tildes o documento)."""
        return await self._workers.search(replace(filters, text=" ".join(filters.text.split())))
