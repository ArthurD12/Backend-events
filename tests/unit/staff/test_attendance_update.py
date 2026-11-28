"""Pruebas unitarias de `UpdateAttendance` (HU18, T-03, plan §3.1 y §7.1).

Cubren el orden lock → 404, `CANCELLED` antes de la ventana y `now == end_at`
permitido (CA-18.1/18.3/18.4), validación del estado (CA-18.2/18.16), primer
registro sin motivo (CA-18.11), idempotencia sin auditoría (CA-18.12), corrección
con motivo obligatorio (CA-18.11) y evento huérfano devuelto con `event=None` sin
404 (CA-18.22). Sin base de datos: fakes en memoria.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

import pytest

from local_eventos.modules.commercial.public_api import EventInfo, EventStatus
from local_eventos.modules.staff.application.attendance_errors import (
    AttendanceAssignmentCancelledError,
    AttendanceNotDueError,
)
from local_eventos.modules.staff.application.errors import AssignmentNotFoundError
from local_eventos.modules.staff.application.ports.attendance_repository import (
    AttendanceAssignmentView,
    AttendanceHistoryRow,
    AttendanceView,
)
from local_eventos.modules.staff.application.use_cases.update_attendance import (
    UpdateAttendance,
)
from local_eventos.modules.staff.domain.attendance import Attendance, AttendanceStatus
from local_eventos.modules.staff.domain.attendance_audit import (
    AttendanceAction,
    AttendanceAudit,
)
from local_eventos.modules.staff.domain.attendance_errors import (
    AttendanceReasonRequiredError,
    AttendanceStatusInvalidError,
)
from local_eventos.modules.staff.domain.enums import (
    AssignmentStatus,
    WorkerFunction,
)

ASSIGNMENT_ID = UUID("11111111-1111-1111-1111-111111111111")
EVENT_ID = UUID("22222222-2222-2222-2222-222222222222")
WORKER_ID = UUID("33333333-3333-3333-3333-333333333333")
ACTOR_ID = UUID("99999999-9999-9999-9999-999999999999")
OTHER_ACTOR_ID = UUID("88888888-8888-8888-8888-888888888888")
NOW = datetime(2026, 11, 28, 18, 0, tzinfo=UTC)
END_AT = datetime(2026, 11, 28, 17, 0, tzinfo=UTC)


def _assignment(
    *,
    status: AssignmentStatus = AssignmentStatus.ACTIVE,
    end_at: datetime = END_AT,
) -> AttendanceAssignmentView:
    return AttendanceAssignmentView(
        assignment_id=ASSIGNMENT_ID,
        event_id=EVENT_ID,
        worker_id=WORKER_ID,
        worker_name="Ana Pérez",
        function=WorkerFunction.WAITER,
        function_description=None,
        start_at=END_AT - timedelta(hours=4),
        end_at=end_at,
        pay_cents=15000,
        currency="PEN",
        assignment_status=status,
    )


def _event(
    *,
    status: EventStatus = EventStatus.SCHEDULED,
    event_date: date = date(2026, 11, 28),
) -> EventInfo:
    return EventInfo(
        id=EVENT_ID,
        code="EV-0001",
        status=status,
        event_date=event_date,
        start_time=time(13, 0),
        end_time=time(17, 0),
    )


class FakeClock:
    """Reloj fijo para que `recorded_at` sea determinista."""

    def __init__(self, now: datetime = NOW) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeEventLookup:
    """Devuelve los eventos sembrados o `None` si no existen (huérfano)."""

    def __init__(self, events: dict[UUID, EventInfo] | None = None) -> None:
        self.events = events if events is not None else {EVENT_ID: _event()}
        self.calls: list[UUID] = []

    async def __call__(self, event_id: UUID) -> EventInfo | None:
        self.calls.append(event_id)
        return self.events.get(event_id)


class FakeAttendanceRepository:
    """Repositorio en memoria con la misma semántica que el puerto."""

    def __init__(
        self,
        assignment: AttendanceAssignmentView | None = None,
        attendance: AttendanceView | None = None,
    ) -> None:
        self.assignment = assignment if assignment is not None else _assignment()
        self.attendance = attendance
        self.audits: list[AttendanceAudit] = []
        self.calls: list[str] = []
        self.saved: list[tuple[Attendance, AttendanceAudit]] = []

    async def lock_assignment(self, assignment_id: UUID) -> AttendanceAssignmentView | None:
        self.calls.append("lock_assignment")
        return self.assignment

    async def get(self, assignment_id: UUID) -> AttendanceView | None:
        self.calls.append("get")
        return self.attendance

    async def save(self, attendance: Attendance, audit: AttendanceAudit) -> None:
        self.calls.append("save")
        self.saved.append((attendance, audit))
        self.audits.append(audit)
        self.attendance = AttendanceView(
            assignment_id=attendance.assignment_id,
            status=attendance.status,
            recorded_by=attendance.recorded_by,
            recorded_at=attendance.recorded_at,
        )

    async def list_history(
        self,
        worker_id: UUID,
        event_id: UUID | None = None,
    ) -> list[AttendanceHistoryRow]:
        return []


def _case(
    *,
    repository: FakeAttendanceRepository | None = None,
    events: FakeEventLookup | None = None,
    now: datetime = NOW,
) -> tuple[UpdateAttendance, FakeAttendanceRepository, FakeEventLookup]:
    repository = repository if repository is not None else FakeAttendanceRepository()
    events = events if events is not None else FakeEventLookup()
    return UpdateAttendance(repository, events, FakeClock(now)), repository, events


async def test_assignment_not_found_returns_404() -> None:
    repository = FakeAttendanceRepository()
    repository.assignment = None
    use_case, _, events = _case(repository=repository)

    with pytest.raises(AssignmentNotFoundError) as error:
        await use_case.execute(
            assignment_id=ASSIGNMENT_ID,
            status=AttendanceStatus.ATTENDED,
            reason=None,
            actor_id=ACTOR_ID,
        )

    assert error.value.code == "staff.assignment_not_found"
    assert repository.calls == ["lock_assignment"]
    assert events.calls == []


async def test_cancelled_is_checked_before_time_window() -> None:
    repository = FakeAttendanceRepository(
        assignment=_assignment(
            status=AssignmentStatus.CANCELLED,
            end_at=NOW + timedelta(hours=2),
        )
    )
    use_case, _, _ = _case(repository=repository)

    with pytest.raises(AttendanceAssignmentCancelledError) as error:
        await use_case.execute(
            assignment_id=ASSIGNMENT_ID,
            status=AttendanceStatus.ATTENDED,
            reason=None,
            actor_id=ACTOR_ID,
        )

    assert error.value.code == "staff.attendance_assignment_cancelled"
    assert repository.calls == ["lock_assignment"]


async def test_not_due_before_end_at_returns_409() -> None:
    repository = FakeAttendanceRepository(assignment=_assignment(end_at=NOW + timedelta(seconds=1)))
    use_case, _, _ = _case(repository=repository)

    with pytest.raises(AttendanceNotDueError) as error:
        await use_case.execute(
            assignment_id=ASSIGNMENT_ID,
            status=AttendanceStatus.ATTENDED,
            reason=None,
            actor_id=ACTOR_ID,
        )

    assert error.value.code == "staff.attendance_not_due"
    assert repository.calls == ["lock_assignment"]


async def test_now_equal_to_end_at_is_accepted() -> None:
    repository = FakeAttendanceRepository(assignment=_assignment(end_at=NOW))
    use_case, _, _ = _case(repository=repository)

    result = await use_case.execute(
        assignment_id=ASSIGNMENT_ID,
        status=AttendanceStatus.ATTENDED,
        reason=None,
        actor_id=ACTOR_ID,
    )

    assert result.attendance.status is AttendanceStatus.ATTENDED
    assert result.attendance.recorded_at == NOW
    assert len(repository.audits) == 1


async def test_first_record_ignores_reason_and_audits_recorded() -> None:
    use_case, repository, _ = _case()

    result = await use_case.execute(
        assignment_id=ASSIGNMENT_ID,
        status="NOT_ATTENDED",
        reason="  no llegó  ",
        actor_id=ACTOR_ID,
    )

    assert result.attendance.status is AttendanceStatus.NOT_ATTENDED
    assert result.attendance.recorded_by == ACTOR_ID
    assert result.attendance.recorded_at == NOW
    assert len(repository.audits) == 1
    audit = repository.audits[0]
    assert audit.action is AttendanceAction.RECORDED
    assert audit.previous_status is None
    assert audit.new_status is AttendanceStatus.NOT_ATTENDED
    assert audit.reason is None


@pytest.mark.parametrize("status", [None, "", "attended", "UNKNOWN", "ATTENDED "])
async def test_invalid_status_returns_422(status: str | None) -> None:
    use_case, repository, events = _case()

    with pytest.raises(AttendanceStatusInvalidError) as error:
        await use_case.execute(
            assignment_id=ASSIGNMENT_ID,
            status=status,
            reason=None,
            actor_id=ACTOR_ID,
        )

    assert error.value.code == "staff.attendance_status_invalid"
    assert repository.calls == ["lock_assignment"]
    assert events.calls == []


async def test_valid_status_as_text_is_accepted() -> None:
    use_case, _, _ = _case()

    result = await use_case.execute(
        assignment_id=ASSIGNMENT_ID,
        status="ATTENDED",
        reason=None,
        actor_id=ACTOR_ID,
    )

    assert result.attendance.status is AttendanceStatus.ATTENDED


async def test_same_status_is_idempotent_without_audit() -> None:
    stored = AttendanceView(
        assignment_id=ASSIGNMENT_ID,
        status=AttendanceStatus.ATTENDED,
        recorded_by=OTHER_ACTOR_ID,
        recorded_at=NOW - timedelta(days=1),
    )
    repository = FakeAttendanceRepository(attendance=stored)
    use_case, _, _ = _case(repository=repository)

    result = await use_case.execute(
        assignment_id=ASSIGNMENT_ID,
        status=AttendanceStatus.ATTENDED,
        reason=None,
        actor_id=ACTOR_ID,
    )

    assert result.attendance == stored
    assert result.attendance.recorded_by == OTHER_ACTOR_ID
    assert repository.audits == []
    assert "save" not in repository.calls


async def test_correction_requires_reason() -> None:
    stored = AttendanceView(
        assignment_id=ASSIGNMENT_ID,
        status=AttendanceStatus.ATTENDED,
        recorded_by=OTHER_ACTOR_ID,
        recorded_at=NOW - timedelta(days=1),
    )
    use_case, repository, _ = _case(repository=FakeAttendanceRepository(attendance=stored))

    with pytest.raises(AttendanceReasonRequiredError) as error:
        await use_case.execute(
            assignment_id=ASSIGNMENT_ID,
            status=AttendanceStatus.NOT_ATTENDED,
            reason=None,
            actor_id=ACTOR_ID,
        )

    assert error.value.code == "staff.attendance_reason_required"
    assert repository.audits == []
    assert "save" not in repository.calls


@pytest.mark.parametrize("reason", ["", "   ", "x" * 501])
async def test_correction_rejects_blank_or_too_long_reason(reason: str) -> None:
    stored = AttendanceView(
        assignment_id=ASSIGNMENT_ID,
        status=AttendanceStatus.ATTENDED,
        recorded_by=OTHER_ACTOR_ID,
        recorded_at=NOW - timedelta(days=1),
    )
    use_case, repository, _ = _case(repository=FakeAttendanceRepository(attendance=stored))

    with pytest.raises(AttendanceReasonRequiredError):
        await use_case.execute(
            assignment_id=ASSIGNMENT_ID,
            status=AttendanceStatus.NOT_ATTENDED,
            reason=reason,
            actor_id=ACTOR_ID,
        )

    assert repository.audits == []


async def test_correction_stores_trimmed_reason_and_audits() -> None:
    stored = AttendanceView(
        assignment_id=ASSIGNMENT_ID,
        status=AttendanceStatus.ATTENDED,
        recorded_by=OTHER_ACTOR_ID,
        recorded_at=NOW - timedelta(days=1),
    )
    use_case, repository, _ = _case(repository=FakeAttendanceRepository(attendance=stored))

    result = await use_case.execute(
        assignment_id=ASSIGNMENT_ID,
        status=AttendanceStatus.NOT_ATTENDED,
        reason="  se retiró antes  ",
        actor_id=ACTOR_ID,
    )

    assert result.attendance.status is AttendanceStatus.NOT_ATTENDED
    assert result.attendance.recorded_by == ACTOR_ID
    assert result.attendance.recorded_at == NOW
    assert len(repository.audits) == 1
    audit = repository.audits[0]
    assert audit.action is AttendanceAction.CORRECTED
    assert audit.previous_status is AttendanceStatus.ATTENDED
    assert audit.new_status is AttendanceStatus.NOT_ATTENDED
    assert audit.reason == "se retiró antes"
    assert audit.actor_id == ACTOR_ID
    assert audit.occurred_at == NOW


async def test_orphan_event_is_tolerated_and_returns_none() -> None:
    use_case, repository, events = _case(events=FakeEventLookup(events={}))

    result = await use_case.execute(
        assignment_id=ASSIGNMENT_ID,
        status=AttendanceStatus.ATTENDED,
        reason=None,
        actor_id=ACTOR_ID,
    )

    assert events.calls == [EVENT_ID]
    assert result.event is None
    assert result.attendance.status is AttendanceStatus.ATTENDED
    assert len(repository.audits) == 1


async def test_orphan_event_on_correction_still_succeeds() -> None:
    stored = AttendanceView(
        assignment_id=ASSIGNMENT_ID,
        status=AttendanceStatus.ATTENDED,
        recorded_by=OTHER_ACTOR_ID,
        recorded_at=NOW - timedelta(days=1),
    )
    use_case, repository, _ = _case(
        repository=FakeAttendanceRepository(attendance=stored),
        events=FakeEventLookup(events={}),
    )

    result = await use_case.execute(
        assignment_id=ASSIGNMENT_ID,
        status=AttendanceStatus.NOT_ATTENDED,
        reason="corrección administrativa",
        actor_id=ACTOR_ID,
    )

    assert result.event is None
    assert repository.audits[0].action is AttendanceAction.CORRECTED


async def test_resolved_event_is_returned() -> None:
    event = _event(status=EventStatus.CANCELLED)
    use_case, _, _ = _case(events=FakeEventLookup({EVENT_ID: event}))

    result = await use_case.execute(
        assignment_id=ASSIGNMENT_ID,
        status=AttendanceStatus.ATTENDED,
        reason=None,
        actor_id=ACTOR_ID,
    )

    assert result.event is event
    assert result.assignment.assignment_id == ASSIGNMENT_ID


async def test_lock_happens_before_get() -> None:
    use_case, repository, _ = _case()

    await use_case.execute(
        assignment_id=ASSIGNMENT_ID,
        status=AttendanceStatus.ATTENDED,
        reason=None,
        actor_id=ACTOR_ID,
    )

    assert repository.calls[:3] == ["lock_assignment", "get", "save"]
