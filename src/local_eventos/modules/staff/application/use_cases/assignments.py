"""Casos de uso de asignaciones de personal a eventos (HU17)."""

from dataclasses import dataclass
from datetime import datetime, time
from uuid import UUID

from local_eventos.modules.staff.application.errors import (
    AssignmentNotFoundError,
    AssignmentOverlapError,
    EventNotAssignableError,
    EventNotFoundError,
    WorkerInactiveError,
    WorkerUnavailableError,
)
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentRepository,
)
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.event_lookup import (
    ASSIGNABLE_STATUSES,
    EventLookup,
)
from local_eventos.modules.staff.application.ports.unavailability_repository import (
    UnavailabilityRepository,
)
from local_eventos.modules.staff.application.ports.worker_repository import WorkerRepository
from local_eventos.modules.staff.application.use_cases.workers import GetWorker
from local_eventos.modules.staff.domain.assignment import EVENT_CANCELLED_REASON, Assignment
from local_eventos.modules.staff.domain.period import Period
from local_eventos.modules.staff.domain.worker import Worker, WorkerFunction


@dataclass(frozen=True)
class AssignWorkerCommand:
    worker_id: UUID
    function: WorkerFunction | None = None  # por defecto, la del trabajador
    start_time: time | None = None  # por defecto, el horario del evento (CA-17.2)
    end_time: time | None = None
    agreed_pay_cents: int | None = None  # por defecto, la tarifa referencial (CA-17.2)


@dataclass(frozen=True)
class AssignedWorker:
    """Asignación con el nombre del trabajador, para el detalle del evento (CA-17.6)."""

    assignment: Assignment
    worker_name: str


class AssignWorker:
    def __init__(
        self,
        workers: WorkerRepository,
        unavailability: UnavailabilityRepository,
        assignments: AssignmentRepository,
        events: EventLookup,
        clock: Clock,
    ) -> None:
        self._workers = workers
        self._unavailability = unavailability
        self._assignments = assignments
        self._events = events
        self._clock = clock

    async def __call__(
        self, event_id: UUID, command: AssignWorkerCommand, *, created_by: UUID
    ) -> AssignedWorker:
        """CA-17.1 a CA-17.5. El cruce se revisa aquí para decir con qué evento choca; si dos
        personas asignan a la vez, la restricción de PostgreSQL rechaza la segunda (RN12)."""
        event = await self._events(event_id)
        if event is None:
            raise EventNotFoundError()
        if event.status not in ASSIGNABLE_STATUSES:
            raise EventNotAssignableError()
        worker = await GetWorker(self._workers)(command.worker_id)
        if not worker.active:
            raise WorkerInactiveError()
        period = Period.on(  # R-STF-4: empieza el día del evento
            event.event_date,
            command.start_time or event.start_time,
            command.end_time or event.end_time,
        )
        assignment = Assignment.create(
            worker_id=worker.id,
            event_id=event.id,
            event_code=event.code,
            function=command.function or worker.function,
            period=period,
            agreed_pay_cents=(
                worker.reference_rate_cents
                if command.agreed_pay_cents is None
                else command.agreed_pay_cents
            ),
            created_by=created_by,
            now=self._clock.now(),
        )
        busy = await self._assignments.list_active_overlapping(period, worker_id=worker.id)
        if busy:
            first = min(busy, key=lambda a: a.period.starts_at)
            raise AssignmentOverlapError(first.event_code, first.period)
        away = await self._unavailability.list_overlapping(period, worker_id=worker.id)
        if away:
            raise WorkerUnavailableError(min(away, key=lambda u: u.period.starts_at).period)
        await self._assignments.add(assignment)
        return AssignedWorker(assignment, worker.name)


class WithdrawAssignment:
    def __init__(self, assignments: AssignmentRepository, clock: Clock) -> None:
        self._assignments = assignments
        self._clock = clock

    async def __call__(
        self, assignment_id: UUID, *, reason: str | None, withdrawn_by: UUID
    ) -> Assignment:
        """CA-17.7: queda registrada como retirada y deja de bloquear el horario."""
        assignment = await self._assignments.get(assignment_id)
        if assignment is None:
            raise AssignmentNotFoundError()
        assignment.withdraw(reason=reason, withdrawn_by=withdrawn_by, now=self._clock.now())
        await self._assignments.update(assignment)
        return assignment


class ListEventAssignments:
    def __init__(self, assignments: AssignmentRepository, workers: WorkerRepository) -> None:
        self._assignments = assignments
        self._workers = workers

    async def __call__(self, event_id: UUID) -> list[AssignedWorker]:
        """CA-17.6: vigentes y retiradas, por hora de inicio."""
        assignments = await self._assignments.list_for_event(event_id)
        workers: dict[UUID, Worker] = {
            w.id: w for w in await self._workers.get_many({a.worker_id for a in assignments})
        }
        return [
            AssignedWorker(a, workers[a.worker_id].name if a.worker_id in workers else "")
            for a in assignments
        ]


class ReleaseEventAssignments:
    """R-STF-5: al cancelar un evento, `commercial` retira sus asignaciones en el mismo paso."""

    def __init__(self, assignments: AssignmentRepository) -> None:
        self._assignments = assignments

    async def __call__(self, event_id: UUID, *, released_by: UUID, now: datetime) -> int:
        """Devuelve cuántas asignaciones vigentes se retiraron."""
        released = 0
        for assignment in await self._assignments.list_for_event(event_id):
            if assignment.is_active:
                assignment.withdraw(
                    reason=EVENT_CANCELLED_REASON, withdrawn_by=released_by, now=now
                )
                await self._assignments.update(assignment)
                released += 1
        return released
