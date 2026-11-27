"""Pruebas del caso de uso `GetStaffAvailability` (HU16, T-11).

Sin base de datos: fakes y espías en memoria. Cubre CA-16.3 (estado por
intervalo), CA-16.4 (filtro por función), CA-16.5 (solo activos), CA-16.7
(asignación que solapa), CA-16.8 (detalle del conflicto sin datos sensibles),
CA-16.9/16.10 (indisponibilidad prevalece y ambos detalles), CA-16.11 (filtros
combinados y resultado vacío), CA-16.12 (libre), CA-16.15 (cancelado no cuenta,
finalizado sí y no se libera) y CA-16.16 (consulta repetible y de solo lectura).

Además verifica que se llama al puerto de solapes de HU17, que `release` nunca se
invoca, que el evento se cachea por petición, que la función se lee con una sola
llamada `by_ids` y que un evento huérfano se omite con warning.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, date, datetime, time
from uuid import UUID

import pytest

from local_eventos.modules.commercial.public_api import EventInfo, EventStatus
from local_eventos.modules.staff.application.ports.assignment_conflict_lookup import (
    AssignmentFunction,
)
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentOverlap,
)
from local_eventos.modules.staff.application.ports.worker_repository import WorkerRef
from local_eventos.modules.staff.application.use_cases.get_staff_availability import (
    AvailabilityConflict,
    AvailabilityItem,
    GetStaffAvailability,
    UnavailabilityDetail,
)
from local_eventos.modules.staff.domain.availability_query import AvailabilityQuery
from local_eventos.modules.staff.domain.enums import (
    AvailabilityState,
    UnavailabilityKind,
    UnavailabilityStatus,
    WorkerFunction,
    WorkerStatus,
)
from local_eventos.modules.staff.domain.errors import AvailabilityWindowInvalidError
from local_eventos.modules.staff.domain.unavailability import Unavailability

WORKER_FREE = UUID("11111111-1111-1111-1111-111111111101")
WORKER_BUSY = UUID("11111111-1111-1111-1111-111111111102")
WORKER_UNAVAILABLE = UUID("11111111-1111-1111-1111-111111111103")
WORKER_INACTIVE = UUID("11111111-1111-1111-1111-111111111104")

EVENT_SCHEDULED = UUID("44444444-4444-4444-4444-444444444401")
EVENT_CONFIRMED = UUID("44444444-4444-4444-4444-444444444402")
EVENT_FINISHED = UUID("44444444-4444-4444-4444-444444444403")
EVENT_CANCELLED = UUID("44444444-4444-4444-4444-444444444404")
EVENT_ORPHAN = UUID("44444444-4444-4444-4444-444444444405")

ASSIGNMENT_A = UUID("55555555-5555-5555-5555-555555555501")
ASSIGNMENT_B = UUID("55555555-5555-5555-5555-555555555502")
ASSIGNMENT_C = UUID("55555555-5555-5555-5555-555555555503")

START_AT = datetime(2026, 12, 19, 23, 0, tzinfo=UTC)
END_AT = datetime(2026, 12, 20, 4, 0, tzinfo=UTC)
EVENT_DATE = date(2026, 12, 19)


def _worker(
    worker_id: UUID,
    name: str,
    *,
    function: WorkerFunction | None = WorkerFunction.WAITER,
    description: str | None = None,
    status: WorkerStatus = WorkerStatus.ACTIVE,
) -> WorkerRef:
    return WorkerRef(
        id=worker_id,
        name=name,
        function=function,
        function_description=description,
        status=status,
    )


def _event(
    event_id: UUID,
    status: EventStatus,
    code: str,
    *,
    event_date: date = EVENT_DATE,
) -> EventInfo:
    return EventInfo(
        id=event_id,
        code=code,
        status=status,
        event_date=event_date,
        start_time=time(18, 0),
        end_time=time(23, 0),
    )


def _overlap(assignment_id: UUID, event_id: UUID) -> AssignmentOverlap:
    return AssignmentOverlap(
        id=assignment_id,
        event_id=event_id,
        start_at=START_AT,
        end_at=END_AT,
    )


def _query(
    *,
    function: WorkerFunction | None = None,
    state: AvailabilityState | None = None,
) -> AvailabilityQuery:
    return AvailabilityQuery(
        from_date=EVENT_DATE,
        to_date=EVENT_DATE,
        start_time=time(18, 0),
        end_time=time(23, 0),
        function=function,
        state=state,
    )


class FakeWorkerRepository:
    """Solo devuelve activos, como el contrato del puerto, y registra el filtro."""

    def __init__(self, workers: list[WorkerRef]) -> None:
        self.workers = workers
        self.function_filters: list[WorkerFunction | None] = []

    async def list_active(self, function: WorkerFunction | None = None) -> list[WorkerRef]:
        self.function_filters.append(function)
        return [
            worker
            for worker in self.workers
            if worker.status is WorkerStatus.ACTIVE
            and (function is None or worker.function is function)
        ]


class FakeUnavailabilityRepository:
    """Aplica el predicado semiabierto y registra las consultas."""

    def __init__(self, items: list[Unavailability] | None = None) -> None:
        self.items = list(items or [])
        self.calls: list[tuple[datetime, datetime, tuple[UUID, ...]]] = []

    async def list_active_overlapping(
        self,
        start_at: datetime,
        end_at: datetime,
        worker_ids: list[UUID],
    ) -> list[Unavailability]:
        self.calls.append((start_at, end_at, tuple(worker_ids)))
        return [
            item
            for item in self.items
            if item.worker_id in worker_ids
            and item.status is UnavailabilityStatus.ACTIVE
            and item.start_at < end_at
            and item.end_at > start_at
        ]


class FakeAssignmentRepository:
    """Espía del puerto de HU17: solapes por trabajador y ninguna escritura."""

    def __init__(self, overlaps: dict[UUID, list[AssignmentOverlap]] | None = None) -> None:
        self.overlaps = overlaps or {}
        self.overlap_calls: list[tuple[UUID, datetime, datetime]] = []
        self.release_calls = 0
        self.save_calls = 0

    async def list_active_overlaps(
        self,
        worker_id: UUID,
        start_at: datetime,
        end_at: datetime,
        *,
        exclude_assignment_id: UUID | None = None,
    ) -> list[AssignmentOverlap]:
        self.overlap_calls.append((worker_id, start_at, end_at))
        return list(self.overlaps.get(worker_id, []))

    async def release(self, assignments: object) -> None:
        self.release_calls += 1

    async def save(self, assignment: object, audit: object) -> None:
        self.save_calls += 1


class FakeEventLookup:
    """Doble de `commercial.public_api.event_lookup` con contador de llamadas."""

    def __init__(self, events: dict[UUID, EventInfo] | None = None) -> None:
        self.events = events or {}
        self.calls: list[UUID] = []

    async def __call__(self, event_id: UUID) -> EventInfo | None:
        self.calls.append(event_id)
        return self.events.get(event_id)


class FakeConflictLookup:
    """Devuelve la función sembrada y registra cada llamada `by_ids`."""

    def __init__(self, functions: dict[UUID, AssignmentFunction | None] | None = None) -> None:
        self.functions = functions or {}
        self.calls: list[list[UUID]] = []

    async def by_ids(self, assignment_ids: list[UUID]) -> dict[UUID, AssignmentFunction | None]:
        self.calls.append(list(assignment_ids))
        return {
            assignment_id: self.functions.get(assignment_id) for assignment_id in assignment_ids
        }


def _build(
    *,
    workers: list[WorkerRef] | None = None,
    unavailabilities: list[Unavailability] | None = None,
    overlaps: dict[UUID, list[AssignmentOverlap]] | None = None,
    events: dict[UUID, EventInfo] | None = None,
    functions: dict[UUID, AssignmentFunction | None] | None = None,
) -> tuple[
    GetStaffAvailability,
    FakeWorkerRepository,
    FakeUnavailabilityRepository,
    FakeAssignmentRepository,
    FakeEventLookup,
    FakeConflictLookup,
]:
    worker_repository = FakeWorkerRepository(
        workers
        if workers is not None
        else [
            _worker(WORKER_FREE, "Ana Libre"),
            _worker(WORKER_BUSY, "Beto Ocupado"),
            _worker(WORKER_UNAVAILABLE, "Carla Ausente"),
        ]
    )
    unavailability_repository = FakeUnavailabilityRepository(unavailabilities)
    assignment_repository = FakeAssignmentRepository(overlaps)
    event_lookup = FakeEventLookup(events)
    conflict_lookup = FakeConflictLookup(functions)
    use_case = GetStaffAvailability(
        worker_repository,
        unavailability_repository,
        assignment_repository,
        event_lookup,
        conflict_lookup,
    )
    return (
        use_case,
        worker_repository,
        unavailability_repository,
        assignment_repository,
        event_lookup,
        conflict_lookup,
    )


def _unavailability(
    worker_id: UUID, *, kind: UnavailabilityKind = UnavailabilityKind.VACATION
) -> Unavailability:
    return Unavailability.register(
        worker_id=worker_id,
        kind=kind,
        start_at=START_AT,
        end_at=END_AT,
    )


async def test_ca16_3_and_16_12_states_in_the_queried_interval() -> None:
    use_case, workers, unavailabilities, assignments, _, _ = _build(
        unavailabilities=[_unavailability(WORKER_UNAVAILABLE)],
        overlaps={WORKER_BUSY: [_overlap(ASSIGNMENT_A, EVENT_SCHEDULED)]},
        events={EVENT_SCHEDULED: _event(EVENT_SCHEDULED, EventStatus.SCHEDULED, "EVT-001")},
        functions={ASSIGNMENT_A: AssignmentFunction(WorkerFunction.WAITER, None)},
    )

    report = await use_case.execute(_query())

    by_name = {item.name: item.state for item in report.items}
    assert by_name == {
        "Ana Libre": AvailabilityState.FREE,
        "Beto Ocupado": AvailabilityState.BUSY,
        "Carla Ausente": AvailabilityState.UNAVAILABLE,
    }
    assert [item.name for item in report.items] == [
        "Ana Libre",
        "Beto Ocupado",
        "Carla Ausente",
    ]
    assert report.start_at == START_AT
    assert report.end_at == END_AT
    assert workers.function_filters == [None]
    assert unavailabilities.calls == [
        (START_AT, END_AT, (WORKER_FREE, WORKER_BUSY, WORKER_UNAVAILABLE))
    ]
    assert [call[0] for call in assignments.overlap_calls] == [
        WORKER_FREE,
        WORKER_BUSY,
        WORKER_UNAVAILABLE,
    ]


async def test_ca16_4_function_filter_is_forwarded_and_applied() -> None:
    use_case, workers, _, assignments, _, _ = _build(
        workers=[
            _worker(WORKER_FREE, "Ana Camarera", function=WorkerFunction.WAITER),
            _worker(WORKER_BUSY, "Beto Cocinero", function=WorkerFunction.COOK),
        ],
    )

    report = await use_case.execute(_query(function=WorkerFunction.COOK))

    assert workers.function_filters == [WorkerFunction.COOK]
    assert [item.name for item in report.items] == ["Beto Cocinero"]
    assert [call[0] for call in assignments.overlap_calls] == [WORKER_BUSY]


async def test_ca16_5_inactive_worker_never_appears() -> None:
    use_case, _, _, assignments, _, _ = _build(
        workers=[
            _worker(WORKER_FREE, "Ana Activa"),
            _worker(WORKER_INACTIVE, "Inés Inactiva", status=WorkerStatus.INACTIVE),
        ],
    )

    report = await use_case.execute(_query())

    assert [item.worker_id for item in report.items] == [WORKER_FREE]
    assert [call[0] for call in assignments.overlap_calls] == [WORKER_FREE]


async def test_ca16_7_assignment_overlap_marks_busy_via_hu17_port() -> None:
    use_case, _, _, assignments, _, _ = _build(
        workers=[_worker(WORKER_BUSY, "Beto Ocupado")],
        overlaps={WORKER_BUSY: [_overlap(ASSIGNMENT_A, EVENT_CONFIRMED)]},
        events={EVENT_CONFIRMED: _event(EVENT_CONFIRMED, EventStatus.CONFIRMED, "EVT-002")},
        functions={ASSIGNMENT_A: AssignmentFunction(WorkerFunction.WAITER, None)},
    )

    report = await use_case.execute(_query())

    assert report.items[0].state is AvailabilityState.BUSY
    assert assignments.overlap_calls == [(WORKER_BUSY, START_AT, END_AT)]
    assert assignments.release_calls == 0


async def test_ca16_8_conflict_detail_without_sensitive_data() -> None:
    use_case, _, _, _, _, _ = _build(
        workers=[_worker(WORKER_BUSY, "Beto Ocupado")],
        overlaps={WORKER_BUSY: [_overlap(ASSIGNMENT_A, EVENT_SCHEDULED)]},
        events={EVENT_SCHEDULED: _event(EVENT_SCHEDULED, EventStatus.SCHEDULED, "EVT-2026-0012")},
        functions={ASSIGNMENT_A: AssignmentFunction(WorkerFunction.BARTENDER, "Barra principal")},
    )

    report = await use_case.execute(_query())

    conflict = report.items[0].conflicts[0]
    assert conflict == AvailabilityConflict(
        event_code="EVT-2026-0012",
        event_date=EVENT_DATE,
        start_time=time(18, 0),
        end_time=time(23, 0),
        function=WorkerFunction.BARTENDER,
        function_description="Barra principal",
    )
    assert {field.name for field in fields(AvailabilityConflict)} == {
        "event_code",
        "event_date",
        "start_time",
        "end_time",
        "function",
        "function_description",
    }
    assert {field.name for field in fields(AvailabilityItem)} == {
        "worker_id",
        "name",
        "function",
        "function_description",
        "state",
        "conflicts",
        "unavailabilities",
    }
    forbidden = {"pay", "pay_cents", "currency", "rate", "document", "document_number", "phone"}
    assert forbidden.isdisjoint(field.name for field in fields(AvailabilityConflict))
    assert forbidden.isdisjoint(field.name for field in fields(UnavailabilityDetail))


async def test_ca16_9_unavailability_marks_unavailable_with_detail() -> None:
    use_case, _, _, _, _, _ = _build(
        workers=[_worker(WORKER_UNAVAILABLE, "Carla Ausente")],
        unavailabilities=[_unavailability(WORKER_UNAVAILABLE, kind=UnavailabilityKind.LEAVE)],
    )

    report = await use_case.execute(_query())

    item = report.items[0]
    assert item.state is AvailabilityState.UNAVAILABLE
    assert item.conflicts == ()
    assert len(item.unavailabilities) == 1
    assert item.unavailabilities[0].kind is UnavailabilityKind.LEAVE
    assert item.unavailabilities[0].start_at == START_AT
    assert item.unavailabilities[0].end_at == END_AT


async def test_ca16_10_unavailable_prevails_and_both_details_are_shown() -> None:
    use_case, _, _, _, _, _ = _build(
        workers=[_worker(WORKER_UNAVAILABLE, "Carla Ausente")],
        unavailabilities=[_unavailability(WORKER_UNAVAILABLE)],
        overlaps={WORKER_UNAVAILABLE: [_overlap(ASSIGNMENT_A, EVENT_SCHEDULED)]},
        events={EVENT_SCHEDULED: _event(EVENT_SCHEDULED, EventStatus.SCHEDULED, "EVT-010")},
        functions={ASSIGNMENT_A: AssignmentFunction(WorkerFunction.WAITER, None)},
    )

    report = await use_case.execute(_query())

    item = report.items[0]
    assert item.state is AvailabilityState.UNAVAILABLE
    assert len(item.unavailabilities) == 1
    assert len(item.conflicts) == 1
    assert item.conflicts[0].event_code == "EVT-010"


async def test_ca16_11_state_and_function_filters_combine_and_can_be_empty() -> None:
    use_case, _, _, _, _, _ = _build(
        workers=[
            _worker(WORKER_FREE, "Ana Camarera", function=WorkerFunction.WAITER),
            _worker(WORKER_BUSY, "Beto Cocinero", function=WorkerFunction.COOK),
        ],
        overlaps={WORKER_BUSY: [_overlap(ASSIGNMENT_A, EVENT_SCHEDULED)]},
        events={EVENT_SCHEDULED: _event(EVENT_SCHEDULED, EventStatus.SCHEDULED, "EVT-011")},
        functions={ASSIGNMENT_A: AssignmentFunction(WorkerFunction.COOK, None)},
    )

    busy_cooks = await use_case.execute(
        _query(function=WorkerFunction.COOK, state=AvailabilityState.BUSY)
    )
    assert [item.name for item in busy_cooks.items] == ["Beto Cocinero"]

    free_cooks = await use_case.execute(
        _query(function=WorkerFunction.COOK, state=AvailabilityState.FREE)
    )
    assert free_cooks.items == []


async def test_ca16_15_cancelled_event_does_not_count_and_finished_event_does() -> None:
    use_case, _, _, assignments, event_lookup, _ = _build(
        workers=[
            _worker(WORKER_FREE, "Ana Libre"),
            _worker(WORKER_BUSY, "Beto Finalizado"),
        ],
        overlaps={
            WORKER_FREE: [_overlap(ASSIGNMENT_A, EVENT_CANCELLED)],
            WORKER_BUSY: [_overlap(ASSIGNMENT_B, EVENT_FINISHED)],
        },
        events={
            EVENT_CANCELLED: _event(EVENT_CANCELLED, EventStatus.CANCELLED, "EVT-CAN"),
            EVENT_FINISHED: _event(EVENT_FINISHED, EventStatus.FINISHED, "EVT-FIN"),
        },
        functions={
            ASSIGNMENT_A: AssignmentFunction(WorkerFunction.WAITER, None),
            ASSIGNMENT_B: AssignmentFunction(WorkerFunction.WAITER, None),
        },
    )

    report = await use_case.execute(_query())

    by_name = {item.name: item.state for item in report.items}
    assert by_name["Ana Libre"] is AvailabilityState.FREE
    assert by_name["Beto Finalizado"] is AvailabilityState.BUSY
    assert [item for item in report.items if item.name == "Ana Libre"][0].conflicts == ()
    # Se consulta el evento cancelado para descartarlo, pero nunca se libera ni escribe.
    assert event_lookup.calls == [EVENT_CANCELLED, EVENT_FINISHED]
    assert assignments.release_calls == 0
    assert assignments.save_calls == 0


async def test_ca16_16_repeated_query_is_identical_and_read_only() -> None:
    use_case, _, unavailabilities, assignments, event_lookup, conflicts = _build(
        workers=[_worker(WORKER_BUSY, "Beto Ocupado")],
        unavailabilities=[_unavailability(WORKER_UNAVAILABLE)],
        overlaps={WORKER_BUSY: [_overlap(ASSIGNMENT_A, EVENT_SCHEDULED)]},
        events={EVENT_SCHEDULED: _event(EVENT_SCHEDULED, EventStatus.SCHEDULED, "EVT-016")},
        functions={ASSIGNMENT_A: AssignmentFunction(WorkerFunction.WAITER, None)},
    )

    first = await use_case.execute(_query())
    second = await use_case.execute(_query())

    assert first == second
    assert assignments.release_calls == 0
    assert assignments.save_calls == 0
    assert len(unavailabilities.calls) == 2
    # El caché es por petición: cada ejecución resuelve el evento una sola vez.
    assert event_lookup.calls == [EVENT_SCHEDULED, EVENT_SCHEDULED]
    assert len(conflicts.calls) == 2


async def test_orphan_event_is_omitted_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    use_case, _, _, assignments, _, _ = _build(
        workers=[_worker(WORKER_BUSY, "Beto Ocupado")],
        overlaps={WORKER_BUSY: [_overlap(ASSIGNMENT_A, EVENT_ORPHAN)]},
        events={},
        functions={ASSIGNMENT_A: AssignmentFunction(WorkerFunction.WAITER, None)},
    )

    with caplog.at_level("WARNING"):
        report = await use_case.execute(_query())

    assert report.items[0].state is AvailabilityState.FREE
    assert report.items[0].conflicts == ()
    assert assignments.release_calls == 0
    assert any(
        "no encontrado" in record.message and record.event_id == str(EVENT_ORPHAN)
        for record in caplog.records
    )


async def test_event_lookup_is_cached_per_request() -> None:
    second_assignment = ASSIGNMENT_C
    use_case, _, _, _, event_lookup, _ = _build(
        workers=[_worker(WORKER_BUSY, "Beto Ocupado")],
        overlaps={
            WORKER_BUSY: [
                _overlap(ASSIGNMENT_A, EVENT_SCHEDULED),
                _overlap(second_assignment, EVENT_SCHEDULED),
            ]
        },
        events={EVENT_SCHEDULED: _event(EVENT_SCHEDULED, EventStatus.SCHEDULED, "EVT-CACHE")},
        functions={
            ASSIGNMENT_A: AssignmentFunction(WorkerFunction.WAITER, None),
            second_assignment: AssignmentFunction(WorkerFunction.WAITER, None),
        },
    )

    report = await use_case.execute(_query())

    assert event_lookup.calls == [EVENT_SCHEDULED]
    assert len(report.items[0].conflicts) == 2


async def test_functions_are_read_in_a_single_by_ids_call() -> None:
    use_case, _, _, _, _, conflicts = _build(
        workers=[
            _worker(WORKER_FREE, "Ana Libre"),
            _worker(WORKER_BUSY, "Beto Ocupado"),
        ],
        overlaps={
            WORKER_FREE: [_overlap(ASSIGNMENT_A, EVENT_SCHEDULED)],
            WORKER_BUSY: [
                _overlap(ASSIGNMENT_B, EVENT_CONFIRMED),
                _overlap(ASSIGNMENT_C, EVENT_FINISHED),
            ],
        },
        events={
            EVENT_SCHEDULED: _event(EVENT_SCHEDULED, EventStatus.SCHEDULED, "EVT-1"),
            EVENT_CONFIRMED: _event(EVENT_CONFIRMED, EventStatus.CONFIRMED, "EVT-2"),
            EVENT_FINISHED: _event(EVENT_FINISHED, EventStatus.FINISHED, "EVT-3"),
        },
        functions={
            ASSIGNMENT_A: AssignmentFunction(WorkerFunction.WAITER, None),
            ASSIGNMENT_B: AssignmentFunction(WorkerFunction.COOK, None),
            ASSIGNMENT_C: AssignmentFunction(WorkerFunction.BARTENDER, None),
        },
    )

    await use_case.execute(_query())

    assert len(conflicts.calls) == 1
    assert set(conflicts.calls[0]) == {ASSIGNMENT_A, ASSIGNMENT_B, ASSIGNMENT_C}


async def test_conflicts_are_sorted_and_workers_by_name() -> None:
    later = datetime(2026, 12, 20, 2, 0, tzinfo=UTC)
    third_assignment = ASSIGNMENT_C
    use_case = GetStaffAvailability(
        FakeWorkerRepository(
            [
                _worker(WORKER_BUSY, "Zoe Última"),
                _worker(WORKER_FREE, "ana Primera"),
            ]
        ),
        FakeUnavailabilityRepository(),
        FakeAssignmentRepository(
            {
                WORKER_BUSY: [
                    AssignmentOverlap(
                        id=ASSIGNMENT_A,
                        event_id=EVENT_SCHEDULED,
                        start_at=later,
                        end_at=later,
                    ),
                    AssignmentOverlap(
                        id=third_assignment,
                        event_id=EVENT_CONFIRMED,
                        start_at=START_AT,
                        end_at=END_AT,
                    ),
                ]
            }
        ),
        FakeEventLookup(
            {
                EVENT_SCHEDULED: _event(EVENT_SCHEDULED, EventStatus.SCHEDULED, "EVT-Z"),
                EVENT_CONFIRMED: _event(EVENT_CONFIRMED, EventStatus.CONFIRMED, "EVT-A"),
            }
        ),
        FakeConflictLookup(
            {
                ASSIGNMENT_A: AssignmentFunction(WorkerFunction.WAITER, None),
                third_assignment: AssignmentFunction(WorkerFunction.WAITER, None),
            }
        ),
    )

    report = await use_case.execute(_query())

    assert [item.name for item in report.items] == ["ana Primera", "Zoe Última"]
    assert [conflict.event_code for conflict in report.items[1].conflicts] == [
        "EVT-A",
        "EVT-Z",
    ]


def test_query_is_validated_at_construction() -> None:
    with pytest.raises(AvailabilityWindowInvalidError):
        AvailabilityQuery(
            from_date=EVENT_DATE,
            to_date=EVENT_DATE,
            start_time=time(18, 0),
        )
