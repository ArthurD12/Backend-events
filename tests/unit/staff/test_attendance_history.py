"""Pruebas unitarias de `GetAttendanceHistory` (HU18, T-04, plan §3.2 y §7.1).

Cubren validación de paginación/rango (CA-18.7), 404 de trabajador y trabajador
inactivo (CA-18.14), filtros `from`/`to`/`event_id` (CA-18.7/18.18), orden
descendente y anuladas con `null` (CA-18.6/18.21), paginación y `total` tras el
filtro (CA-18.8) y evento huérfano (CA-18.22): se conserva con `event=None`, se
excluye con `from`/`to`, se incluye sin filtro de fecha y con `event_id`, y el
`total` lo refleja. Sin base de datos: fakes en memoria.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

import pytest

from local_eventos.modules.commercial.public_api import EventInfo, EventStatus
from local_eventos.modules.staff.application.attendance_errors import (
    AttendanceDateRangeInvalidError,
    AttendanceWorkerNotFoundError,
)
from local_eventos.modules.staff.application.ports.attendance_repository import (
    AttendanceHistoryRow,
)
from local_eventos.modules.staff.application.ports.worker_repository import WorkerRef
from local_eventos.modules.staff.application.use_cases.get_attendance_history import (
    GetAttendanceHistory,
)
from local_eventos.modules.staff.domain.attendance import AttendanceStatus
from local_eventos.modules.staff.domain.enums import (
    AssignmentStatus,
    WorkerFunction,
    WorkerStatus,
)

WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_WORKER_ID = UUID("12121212-1212-1212-1212-121212121212")
ACTOR_ID = UUID("99999999-9999-9999-9999-999999999999")
EVENT_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
EVENT_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
EVENT_C = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
ORPHAN_EVENT = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
NOW = datetime(2026, 11, 28, 18, 0, tzinfo=UTC)


def _worker(
    *,
    worker_id: UUID = WORKER_ID,
    status: WorkerStatus = WorkerStatus.ACTIVE,
) -> WorkerRef:
    return WorkerRef(
        id=worker_id,
        name="Ana Pérez",
        function=WorkerFunction.WAITER,
        function_description=None,
        status=status,
    )


def _event(
    event_id: UUID,
    *,
    event_date: date,
    status: EventStatus = EventStatus.SCHEDULED,
    code: str = "EV-0001",
) -> EventInfo:
    return EventInfo(
        id=event_id,
        code=code,
        status=status,
        event_date=event_date,
        start_time=time(13, 0),
        end_time=time(17, 0),
    )


def _row(
    *,
    event_id: UUID,
    start_at: datetime,
    status: AssignmentStatus = AssignmentStatus.ACTIVE,
    attendance_status: AttendanceStatus | None = None,
    recorded_at: datetime | None = None,
    recorded_by: UUID | None = None,
    worker_id: UUID = WORKER_ID,
) -> AttendanceHistoryRow:
    return AttendanceHistoryRow(
        assignment_id=UUID(int=(event_id.int ^ int(start_at.timestamp())) & ((1 << 128) - 1)),
        event_id=event_id,
        worker_id=worker_id,
        worker_name="Ana Pérez",
        function=WorkerFunction.WAITER,
        function_description=None,
        start_at=start_at,
        end_at=start_at + timedelta(hours=4),
        pay_cents=15000,
        currency="PEN",
        assignment_status=status,
        attendance_status=attendance_status,
        recorded_at=recorded_at,
        recorded_by=recorded_by,
    )


class FakeWorkerLookup:
    """Devuelve las referencias sembradas, incluidas las inactivas."""

    def __init__(self, workers: dict[UUID, WorkerRef] | None = None) -> None:
        self.workers = workers if workers is not None else {WORKER_ID: _worker()}

    async def get(self, worker_id: UUID) -> WorkerRef | None:
        return self.workers.get(worker_id)


class FakeEventLookup:
    """Resuelve eventos y cuenta las llamadas para verificar la deduplicación."""

    def __init__(self, events: dict[UUID, EventInfo] | None = None) -> None:
        self.events = events if events is not None else {}
        self.calls: list[UUID] = []

    async def __call__(self, event_id: UUID) -> EventInfo | None:
        self.calls.append(event_id)
        return self.events.get(event_id)


class FakeAttendanceRepository:
    """Repositorio en memoria: filtra `event_id` en «SQL» y conserva el orden."""

    def __init__(self, rows: list[AttendanceHistoryRow]) -> None:
        self.rows = rows
        self.calls: list[tuple[UUID, UUID | None]] = []

    async def lock_assignment(self, assignment_id: UUID) -> None:
        return None

    async def get(self, assignment_id: UUID) -> None:
        return None

    async def save(self, attendance: object, audit: object) -> None:
        return None

    async def list_history(
        self,
        worker_id: UUID,
        event_id: UUID | None = None,
    ) -> list[AttendanceHistoryRow]:
        self.calls.append((worker_id, event_id))
        rows = [row for row in self.rows if row.worker_id == worker_id]
        if event_id is not None:
            rows = [row for row in rows if row.event_id == event_id]
        return rows


def _case(
    rows: list[AttendanceHistoryRow],
    *,
    workers: FakeWorkerLookup | None = None,
    events: FakeEventLookup | None = None,
) -> tuple[GetAttendanceHistory, FakeAttendanceRepository, FakeEventLookup]:
    repository = FakeAttendanceRepository(rows)
    events = events if events is not None else FakeEventLookup()
    use_case = GetAttendanceHistory(
        repository,
        workers if workers is not None else FakeWorkerLookup(),
        events,
    )
    return use_case, repository, events


@pytest.mark.parametrize(
    ("page", "page_size"),
    [(0, 20), (-1, 20), (1, 0), (1, 101), (1, -5)],
)
async def test_invalid_pagination_returns_422(page: int, page_size: int) -> None:
    use_case, repository, _ = _case([])

    with pytest.raises(AttendanceDateRangeInvalidError) as error:
        await use_case.execute(worker_id=WORKER_ID, page=page, page_size=page_size)

    assert error.value.code == "staff.attendance_date_range_invalid"
    assert repository.calls == []


async def test_from_after_to_returns_422() -> None:
    use_case, repository, _ = _case([])

    with pytest.raises(AttendanceDateRangeInvalidError):
        await use_case.execute(
            worker_id=WORKER_ID,
            from_=date(2026, 12, 2),
            to_=date(2026, 12, 1),
        )

    assert repository.calls == []


async def test_worker_not_found_returns_404() -> None:
    use_case, repository, _ = _case([], workers=FakeWorkerLookup({}))

    with pytest.raises(AttendanceWorkerNotFoundError) as error:
        await use_case.execute(worker_id=WORKER_ID)

    assert error.value.code == "staff.worker_not_found"
    assert repository.calls == []


async def test_inactive_worker_keeps_history() -> None:
    rows = [_row(event_id=EVENT_A, start_at=NOW)]
    workers = FakeWorkerLookup({WORKER_ID: _worker(status=WorkerStatus.INACTIVE)})
    use_case, _, events = _case(
        rows,
        workers=workers,
        events=FakeEventLookup({EVENT_A: _event(EVENT_A, event_date=date(2026, 11, 28))}),
    )

    page = await use_case.execute(worker_id=WORKER_ID)

    assert page.total == 1
    assert page.items[0].row.worker_id == WORKER_ID
    assert events.calls == [EVENT_A]


async def test_cancelled_and_unrecorded_row_has_null_attendance() -> None:
    rows = [
        _row(
            event_id=EVENT_A,
            start_at=NOW,
            status=AssignmentStatus.CANCELLED,
            attendance_status=None,
        )
    ]
    use_case, _, _ = _case(
        rows,
        events=FakeEventLookup({EVENT_A: _event(EVENT_A, event_date=date(2026, 11, 28))}),
    )

    page = await use_case.execute(worker_id=WORKER_ID)

    item = page.items[0]
    assert item.row.assignment_status is AssignmentStatus.CANCELLED
    assert item.row.attendance_status is None
    assert item.row.recorded_at is None
    assert item.row.recorded_by is None


async def test_event_lookup_is_deduplicated_by_event_id() -> None:
    rows = [
        _row(event_id=EVENT_A, start_at=NOW),
        _row(event_id=EVENT_A, start_at=NOW - timedelta(days=1)),
        _row(event_id=EVENT_B, start_at=NOW - timedelta(days=2)),
    ]
    events = FakeEventLookup(
        {
            EVENT_A: _event(EVENT_A, event_date=date(2026, 11, 28)),
            EVENT_B: _event(EVENT_B, event_date=date(2026, 11, 26)),
        }
    )
    use_case, _, _ = _case(rows, events=events)

    page = await use_case.execute(worker_id=WORKER_ID)

    assert events.calls == [EVENT_A, EVENT_B]
    assert page.total == 3
    assert page.items[0].event is not None


async def test_order_from_repository_is_preserved() -> None:
    newest = _row(event_id=EVENT_A, start_at=NOW)
    older = _row(event_id=EVENT_B, start_at=NOW - timedelta(days=2))
    use_case, _, _ = _case(
        [newest, older],
        events=FakeEventLookup(
            {
                EVENT_A: _event(EVENT_A, event_date=date(2026, 11, 28)),
                EVENT_B: _event(EVENT_B, event_date=date(2026, 11, 26)),
            }
        ),
    )

    page = await use_case.execute(worker_id=WORKER_ID)

    assert [item.row.start_at for item in page.items] == [NOW, NOW - timedelta(days=2)]


async def test_event_id_filter_is_passed_to_repository() -> None:
    rows = [
        _row(event_id=EVENT_A, start_at=NOW),
        _row(event_id=EVENT_B, start_at=NOW - timedelta(days=1)),
    ]
    use_case, repository, events = _case(
        rows,
        events=FakeEventLookup(
            {
                EVENT_A: _event(EVENT_A, event_date=date(2026, 11, 28)),
                EVENT_B: _event(EVENT_B, event_date=date(2026, 11, 27)),
            }
        ),
    )

    page = await use_case.execute(worker_id=WORKER_ID, event_id=EVENT_B)

    assert repository.calls == [(WORKER_ID, EVENT_B)]
    assert page.total == 1
    assert events.calls == [EVENT_B]
    assert page.items[0].row.event_id == EVENT_B


async def test_date_filter_is_inclusive_and_excludes_orphans() -> None:
    rows = [
        _row(event_id=EVENT_A, start_at=NOW),
        _row(event_id=EVENT_B, start_at=NOW - timedelta(days=1)),
        _row(event_id=ORPHAN_EVENT, start_at=NOW - timedelta(days=2)),
    ]
    events = FakeEventLookup(
        {
            EVENT_A: _event(EVENT_A, event_date=date(2026, 12, 1)),
            EVENT_B: _event(EVENT_B, event_date=date(2026, 12, 3)),
        }
    )
    use_case, _, _ = _case(rows, events=events)

    page = await use_case.execute(
        worker_id=WORKER_ID,
        from_=date(2026, 12, 1),
        to_=date(2026, 12, 1),
    )

    assert page.total == 1
    assert page.items[0].row.event_id == EVENT_A


async def test_orphan_rows_included_without_date_filter() -> None:
    rows = [
        _row(event_id=EVENT_A, start_at=NOW),
        _row(event_id=ORPHAN_EVENT, start_at=NOW - timedelta(days=1)),
    ]
    events = FakeEventLookup({EVENT_A: _event(EVENT_A, event_date=date(2026, 11, 28))})
    use_case, _, _ = _case(rows, events=events)

    page = await use_case.execute(worker_id=WORKER_ID)

    assert page.total == 2
    assert page.items[1].row.event_id == ORPHAN_EVENT
    assert page.items[1].event is None


async def test_orphan_rows_included_with_event_id_filter() -> None:
    rows = [
        _row(event_id=EVENT_A, start_at=NOW),
        _row(event_id=ORPHAN_EVENT, start_at=NOW - timedelta(days=1)),
    ]
    events = FakeEventLookup({EVENT_A: _event(EVENT_A, event_date=date(2026, 11, 28))})
    use_case, _, _ = _case(rows, events=events)

    page = await use_case.execute(worker_id=WORKER_ID, event_id=ORPHAN_EVENT)

    assert page.total == 1
    assert page.items[0].event is None
    assert page.items[0].row.event_id == ORPHAN_EVENT


async def test_total_is_computed_after_filter_and_pagination() -> None:
    rows = [_row(event_id=EVENT_A, start_at=NOW - timedelta(days=offset)) for offset in range(5)]
    events = FakeEventLookup(
        {
            EVENT_A: _event(EVENT_A, event_date=date(2026, 12, 1)),
            EVENT_B: _event(EVENT_B, event_date=date(2026, 12, 2)),
        }
    )
    rows.append(_row(event_id=EVENT_B, start_at=NOW - timedelta(days=10)))
    use_case, _, _ = _case(rows, events=events)

    page = await use_case.execute(
        worker_id=WORKER_ID,
        from_=date(2026, 12, 1),
        to_=date(2026, 12, 1),
        page=2,
        page_size=2,
    )

    assert page.total == 5
    assert page.page == 2
    assert page.page_size == 2
    assert len(page.items) == 2


async def test_page_out_of_range_returns_empty_with_total() -> None:
    rows = [_row(event_id=EVENT_A, start_at=NOW - timedelta(days=offset)) for offset in range(3)]
    use_case, _, _ = _case(
        rows,
        events=FakeEventLookup({EVENT_A: _event(EVENT_A, event_date=date(2026, 11, 28))}),
    )

    page = await use_case.execute(worker_id=WORKER_ID, page=5, page_size=2)

    assert page.items == []
    assert page.total == 3


async def test_only_from_filter_excludes_older_and_orphans() -> None:
    rows = [
        _row(event_id=EVENT_A, start_at=NOW),
        _row(event_id=EVENT_B, start_at=NOW - timedelta(days=1)),
        _row(event_id=ORPHAN_EVENT, start_at=NOW - timedelta(days=2)),
    ]
    events = FakeEventLookup(
        {
            EVENT_A: _event(EVENT_A, event_date=date(2026, 12, 5)),
            EVENT_B: _event(EVENT_B, event_date=date(2026, 11, 1)),
        }
    )
    use_case, _, _ = _case(rows, events=events)

    page = await use_case.execute(worker_id=WORKER_ID, from_=date(2026, 12, 1))

    assert page.total == 1
    assert page.items[0].row.event_id == EVENT_A


async def test_only_to_filter_excludes_newer_and_orphans() -> None:
    rows = [
        _row(event_id=EVENT_A, start_at=NOW),
        _row(event_id=EVENT_B, start_at=NOW - timedelta(days=1)),
        _row(event_id=EVENT_C, start_at=NOW - timedelta(days=2)),
    ]
    events = FakeEventLookup(
        {
            EVENT_A: _event(EVENT_A, event_date=date(2026, 12, 5)),
            EVENT_B: _event(EVENT_B, event_date=date(2026, 11, 1)),
            EVENT_C: _event(EVENT_C, event_date=date(2026, 12, 5)),
        }
    )
    use_case, _, _ = _case(rows, events=events)

    page = await use_case.execute(worker_id=WORKER_ID, to_=date(2026, 11, 1))

    assert page.total == 1
    assert page.items[0].row.event_id == EVENT_B


async def test_other_workers_rows_are_not_returned_by_fake() -> None:
    rows = [
        _row(event_id=EVENT_A, start_at=NOW),
        _row(event_id=EVENT_B, start_at=NOW, worker_id=OTHER_WORKER_ID),
    ]
    use_case, _, _ = _case(
        rows,
        events=FakeEventLookup(
            {
                EVENT_A: _event(EVENT_A, event_date=date(2026, 11, 28)),
                EVENT_B: _event(EVENT_B, event_date=date(2026, 11, 27)),
            }
        ),
    )

    page = await use_case.execute(worker_id=WORKER_ID)

    assert page.total == 1
