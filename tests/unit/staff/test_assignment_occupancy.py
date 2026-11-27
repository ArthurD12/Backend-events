"""Pruebas del servicio de ocupación de asignaciones (HU17, T-06, CA-17.20).

Usan un repositorio y un `EventLookup` fake: sin base de datos ni `commercial`.
Verifican que solo se liberan asignaciones de eventos `CANCELLED`, que un evento
inexistente no libera, la idempotencia, la persistencia única y que no se escribe
auditoría. También que `has_future` delega con el momento recibido.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from local_eventos.modules.commercial.public_api import EventInfo, EventStatus
from local_eventos.modules.staff.application.assignment_occupancy import (
    AssignmentOccupancy,
)
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentOverlap,
    AssignmentRepository,
    AssignmentView,
)
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import AssignmentAudit
from local_eventos.modules.staff.domain.enums import AssignmentStatus, WorkerFunction

WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
START_AT = datetime(2026, 12, 1, 18, 0, tzinfo=UTC)
END_AT = datetime(2026, 12, 1, 23, 0, tzinfo=UTC)


class FakeAssignmentRepository:
    """Repositorio en memoria que registra las liberaciones persistidas."""

    def __init__(self) -> None:
        self.assignments: dict[UUID, Assignment] = {}
        self.audits: list[AssignmentAudit] = []
        self.release_calls: list[list[Assignment]] = []
        self.has_future_calls: list[tuple[UUID, datetime]] = []

    async def lock_worker(self, worker_id: UUID) -> None:
        raise NotImplementedError

    async def save(self, assignment: Assignment, audit: AssignmentAudit) -> None:
        raise NotImplementedError

    async def get(self, assignment_id: UUID) -> Assignment | None:
        raise NotImplementedError

    async def get_for_update(self, assignment_id: UUID) -> Assignment | None:
        raise NotImplementedError

    async def list_active_overlaps(
        self,
        worker_id: UUID,
        start_at: datetime,
        end_at: datetime,
        *,
        exclude_assignment_id: UUID | None = None,
    ) -> list[AssignmentOverlap]:
        raise NotImplementedError

    async def list_by_event(self, event_id: UUID) -> list[AssignmentView]:
        raise NotImplementedError

    async def list_occupying(self, worker_id: UUID) -> list[Assignment]:
        return [
            assignment
            for assignment in self.assignments.values()
            if assignment.worker_id == worker_id
            and assignment.status is AssignmentStatus.ACTIVE
            and assignment.occupies
        ]

    async def release(self, assignments: Sequence[Assignment]) -> None:
        self.release_calls.append(list(assignments))
        for assignment in assignments:
            assignment.release()

    async def has_active_ending_after(self, worker_id: UUID, moment: datetime) -> bool:
        self.has_future_calls.append((worker_id, moment))
        return any(
            assignment.worker_id == worker_id
            and assignment.status is AssignmentStatus.ACTIVE
            and assignment.occupies
            and assignment.end_at > moment
            for assignment in self.assignments.values()
        )

    async def get_view(self, assignment_id: UUID) -> AssignmentView | None:
        raise NotImplementedError


class FakeEventLookup:
    """Lookup de eventos por id; los que no estén en el mapa devuelven `None`."""

    def __init__(self, events: dict[UUID, EventStatus]) -> None:
        self._events = events
        self.calls: list[UUID] = []

    async def __call__(self, event_id: UUID) -> EventInfo | None:
        self.calls.append(event_id)
        status = self._events.get(event_id)
        if status is None:
            return None
        return EventInfo(
            id=event_id,
            code="EV-001",
            status=status,
            event_date=START_AT.date(),
            start_time=START_AT.time(),
            end_time=END_AT.time(),
        )


def _event_id(index: int) -> UUID:
    return UUID(f"{index:08d}-0000-0000-0000-000000000000")


def _add_assignment(
    repository: FakeAssignmentRepository,
    event_id: UUID,
    *,
    worker_id: UUID = WORKER_ID,
) -> Assignment:
    assignment = Assignment.register(
        event_id=event_id,
        worker_id=worker_id,
        function=WorkerFunction.WAITER,
        start_at=START_AT,
        end_at=END_AT,
        pay=15000,
    )
    repository.assignments[assignment.id] = assignment
    return assignment


def _service(
    repository: FakeAssignmentRepository,
    events: dict[UUID, EventStatus],
) -> AssignmentOccupancy:
    lookup = FakeEventLookup(events)
    return AssignmentOccupancy(repository, lookup)


async def test_libera_solo_asignaciones_de_eventos_cancelados() -> None:
    repository = FakeAssignmentRepository()
    statuses = {
        EventStatus.CANCELLED: _event_id(1),
        EventStatus.SCHEDULED: _event_id(2),
        EventStatus.CONFIRMED: _event_id(3),
        EventStatus.IN_PROGRESS: _event_id(4),
        EventStatus.FINISHED: _event_id(5),
    }
    assignments = {
        status: _add_assignment(repository, event_id) for status, event_id in statuses.items()
    }
    service = _service(repository, {event_id: status for status, event_id in statuses.items()})

    released = await service.release_cancelled(WORKER_ID)

    assert released == 1
    assert assignments[EventStatus.CANCELLED].occupies is False
    assert assignments[EventStatus.CANCELLED].status is AssignmentStatus.ACTIVE
    for status in (
        EventStatus.SCHEDULED,
        EventStatus.CONFIRMED,
        EventStatus.IN_PROGRESS,
        EventStatus.FINISHED,
    ):
        assert assignments[status].occupies is True
    assert repository.release_calls == [[assignments[EventStatus.CANCELLED]]]


async def test_evento_inexistente_no_libera() -> None:
    repository = FakeAssignmentRepository()
    assignment = _add_assignment(repository, _event_id(1))
    service = _service(repository, {})

    released = await service.release_cancelled(WORKER_ID)

    assert released == 0
    assert assignment.occupies is True
    assert repository.release_calls == []


async def test_es_idempotente_y_persiste_una_sola_vez() -> None:
    repository = FakeAssignmentRepository()
    cancelled = _add_assignment(repository, _event_id(1))
    _add_assignment(repository, _event_id(2))
    service = _service(
        repository,
        {_event_id(1): EventStatus.CANCELLED, _event_id(2): EventStatus.CONFIRMED},
    )

    first = await service.release_cancelled(WORKER_ID)
    second = await service.release_cancelled(WORKER_ID)

    assert first == 1
    assert second == 0
    assert repository.release_calls == [[cancelled]]
    assert repository.audits == []


async def test_libera_varias_asignaciones_canceladas() -> None:
    repository = FakeAssignmentRepository()
    first = _add_assignment(repository, _event_id(1))
    second = _add_assignment(repository, _event_id(2))
    service = _service(
        repository,
        {_event_id(1): EventStatus.CANCELLED, _event_id(2): EventStatus.CANCELLED},
    )

    released = await service.release_cancelled(WORKER_ID)

    assert released == 2
    assert repository.release_calls == [[first, second]]
    assert first.occupies is False
    assert second.occupies is False


async def test_ignora_asignaciones_de_otro_trabajador() -> None:
    repository = FakeAssignmentRepository()
    own = _add_assignment(repository, _event_id(1))
    other = _add_assignment(repository, _event_id(2), worker_id=OTHER_WORKER_ID)
    service = _service(
        repository,
        {_event_id(1): EventStatus.CANCELLED, _event_id(2): EventStatus.CANCELLED},
    )

    released = await service.release_cancelled(WORKER_ID)

    assert released == 1
    assert own.occupies is False
    assert other.occupies is True


async def test_has_future_delega_respetando_el_momento() -> None:
    repository = FakeAssignmentRepository()
    _add_assignment(repository, _event_id(1))
    service = _service(repository, {})

    before_end = datetime(2026, 12, 1, 22, 59, tzinfo=UTC)
    after_end = datetime(2026, 12, 2, 0, 0, tzinfo=UTC)

    assert await service.has_future(WORKER_ID, before_end) is True
    assert await service.has_future(WORKER_ID, after_end) is False
    assert repository.has_future_calls == [
        (WORKER_ID, before_end),
        (WORKER_ID, after_end),
    ]


async def test_fake_implementa_el_puerto() -> None:
    repository: AssignmentRepository = FakeAssignmentRepository()
    assert repository is not None
