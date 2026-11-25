"""Personal en memoria para probar sin base de datos."""

from collections.abc import Collection
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

from local_eventos.modules.staff.application.errors import (
    AssignmentOverlapError,
    DocumentTakenError,
)
from local_eventos.modules.staff.application.ports.worker_repository import WorkerFilters
from local_eventos.modules.staff.application.search_text import normalize
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.period import Period
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.worker import Worker, WorkerDocument


class InMemoryWorkerRepository:
    def __init__(self) -> None:
        self.workers: dict[UUID, Worker] = {}

    async def get(self, worker_id: UUID) -> Worker | None:
        worker = self.workers.get(worker_id)
        return replace(worker) if worker else None

    async def get_many(self, worker_ids: Collection[UUID]) -> list[Worker]:
        return [replace(self.workers[i]) for i in worker_ids if i in self.workers]

    async def get_by_document(self, document: WorkerDocument) -> Worker | None:
        return next((replace(w) for w in self.workers.values() if w.document == document), None)

    async def add(self, worker: Worker) -> None:
        self._check_document(worker)
        self.workers[worker.id] = replace(worker)

    async def update(self, worker: Worker) -> None:
        self._check_document(worker)
        self.workers[worker.id] = replace(worker)

    async def search(self, filters: WorkerFilters) -> list[Worker]:
        text = normalize(filters.text)
        return [
            replace(w)
            for w in sorted(self.workers.values(), key=lambda w: w.name)
            if (not text or text in normalize(w.name) or filters.text in w.document.number)
            and (filters.function is None or w.function is filters.function)
            and (filters.worker_type is None or w.worker_type is filters.worker_type)
            and (filters.active is None or w.active is filters.active)
        ]

    def _check_document(self, worker: Worker) -> None:
        if any(w.document == worker.document and w.id != worker.id for w in self.workers.values()):
            raise DocumentTakenError()


class InMemoryUnavailabilityRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Unavailability] = {}

    async def get(self, unavailability_id: UUID) -> Unavailability | None:
        return self.items.get(unavailability_id)

    async def add(self, unavailability: Unavailability) -> None:
        self.items[unavailability.id] = unavailability

    async def remove(self, unavailability_id: UUID) -> None:
        self.items.pop(unavailability_id, None)

    async def list_for_worker(self, worker_id: UUID) -> list[Unavailability]:
        return sorted(
            (u for u in self.items.values() if u.worker_id == worker_id),
            key=lambda u: u.period.starts_at,
        )

    async def list_overlapping(
        self, period: Period, *, worker_id: UUID | None = None
    ) -> list[Unavailability]:
        return [
            u
            for u in self.items.values()
            if u.period.overlaps(period) and worker_id in (None, u.worker_id)
        ]


class InMemoryAssignmentRepository:
    """Imita la restricción de exclusión de PostgreSQL (RN12)."""

    def __init__(self) -> None:
        self.items: dict[UUID, Assignment] = {}

    async def get(self, assignment_id: UUID) -> Assignment | None:
        item = self.items.get(assignment_id)
        return replace(item) if item else None

    async def add(self, assignment: Assignment) -> None:
        if await self.list_active_overlapping(assignment.period, worker_id=assignment.worker_id):
            raise AssignmentOverlapError()
        self.items[assignment.id] = replace(assignment)

    async def update(self, assignment: Assignment) -> None:
        self.items[assignment.id] = replace(assignment)

    async def list_for_event(self, event_id: UUID) -> list[Assignment]:
        return sorted(
            (replace(a) for a in self.items.values() if a.event_id == event_id),
            key=lambda a: a.period.starts_at,
        )

    async def list_active_overlapping(
        self, period: Period, *, worker_id: UUID | None = None
    ) -> list[Assignment]:
        return [
            replace(a)
            for a in self.items.values()
            if a.is_active and a.period.overlaps(period) and worker_id in (None, a.worker_id)
        ]


@dataclass(frozen=True)
class FakeEvent:
    id: UUID
    code: str
    status: str
    event_date: date
    start_time: time
    end_time: time


class FakeEventLookup:
    def __init__(self) -> None:
        self.events: dict[UUID, FakeEvent] = {}

    def add(
        self,
        code: str = "EVT-2026-0001",
        *,
        status: str = "SCHEDULED",
        day: date = date(2026, 12, 19),
        start: time = time(20),
        end: time = time(3),
    ) -> FakeEvent:
        event = FakeEvent(uuid4(), code, status, day, start, end)
        self.events[event.id] = event
        return event

    async def __call__(self, event_id: UUID) -> FakeEvent | None:
        return self.events.get(event_id)


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 11, 25, 15, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> None:
        self.current += timedelta(**delta)
