"""Casos de uso de disponibilidad del personal (HU16)."""

from dataclasses import dataclass
from datetime import date, time
from uuid import UUID

from local_eventos.modules.staff.application.errors import UnavailabilityNotFoundError
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentRepository,
)
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.unavailability_repository import (
    UnavailabilityRepository,
)
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerFilters,
    WorkerRepository,
)
from local_eventos.modules.staff.application.use_cases.workers import GetWorker
from local_eventos.modules.staff.domain.availability import Availability
from local_eventos.modules.staff.domain.period import Period
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.worker import WorkerFunction


@dataclass(frozen=True)
class UnavailabilityCommand:
    day: date
    start_time: time
    end_time: time  # si es menor que el inicio, termina al día siguiente
    reason: str | None = None


class AddUnavailability:
    def __init__(
        self, workers: WorkerRepository, unavailability: UnavailabilityRepository, clock: Clock
    ) -> None:
        self._workers = workers
        self._unavailability = unavailability
        self._clock = clock

    async def __call__(
        self, worker_id: UUID, command: UnavailabilityCommand, *, created_by: UUID
    ) -> Unavailability:
        """CA-16.1."""
        worker = await GetWorker(self._workers)(worker_id)
        unavailability = Unavailability.create(
            worker_id=worker.id,
            period=Period.on(command.day, command.start_time, command.end_time),
            reason=command.reason,
            created_by=created_by,
            now=self._clock.now(),
        )
        await self._unavailability.add(unavailability)
        return unavailability


class RemoveUnavailability:
    def __init__(self, unavailability: UnavailabilityRepository) -> None:
        self._unavailability = unavailability

    async def __call__(self, unavailability_id: UUID) -> None:
        """CA-16.1: es un aviso del trabajador, no una operación con historial."""
        if await self._unavailability.get(unavailability_id) is None:
            raise UnavailabilityNotFoundError()
        await self._unavailability.remove(unavailability_id)


class ListUnavailability:
    def __init__(self, workers: WorkerRepository, unavailability: UnavailabilityRepository) -> None:
        self._workers = workers
        self._unavailability = unavailability

    async def __call__(self, worker_id: UUID) -> list[Unavailability]:
        worker = await GetWorker(self._workers)(worker_id)
        return await self._unavailability.list_for_worker(worker.id)


class CheckAvailability:
    def __init__(
        self,
        workers: WorkerRepository,
        unavailability: UnavailabilityRepository,
        assignments: AssignmentRepository,
    ) -> None:
        self._workers = workers
        self._unavailability = unavailability
        self._assignments = assignments

    async def __call__(
        self, day: date, start: time, end: time, function: WorkerFunction | None = None
    ) -> list[Availability]:
        """CA-16.2 a CA-16.4: solo activos, cada uno libre, ocupado o no disponible."""
        period = Period.on(day, start, end)
        workers = await self._workers.search(WorkerFilters(function=function, active=True))
        assignments = await self._assignments.list_active_overlapping(period)
        unavailability = await self._unavailability.list_overlapping(period)
        return [Availability.of(w, period, assignments, unavailability) for w in workers]
