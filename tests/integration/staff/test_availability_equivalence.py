"""Equivalencia HU16/HU17 de ocupación contra PostgreSQL real (CA-16.21, T-10).

Levanta un trabajador por cada estado de evento (`SCHEDULED`, `CONFIRMED`,
`IN_PROGRESS`, `FINISHED` y `CANCELLED`) con una asignación activa que ocupa en la
misma ventana UTC. Para varias ventanas de `AvailabilityQuery` compara el conjunto
`BUSY` que devuelve `GetStaffAvailability` con el conjunto de trabajadores para los
que `RegisterAssignment` responde `409 staff.assignment_overlap` al intentar una
asignación equivalente sobre un evento candidato `SCHEDULED` solapado. Un evento
`CANCELLED` no bloquea en ninguno de los dos caminos; `FINISHED` sí ocupa.

También toma un snapshot de `occupies`, de las filas de asignaciones y del número de
filas de auditoría antes y después de las consultas de disponibilidad para comprobar
que HU16 no escribe (R-DIS-1). Los eventos se resuelven con el doble en memoria de
`commercial.public_api` que ya usan los tests de asignaciones; este módulo nunca lee
tablas de `commercial`.

`GetStaffAvailability` se cablea con los puertos reales y el doble en memoria de
eventos de `commercial.public_api` (T-11). Necesita Docker/PostgreSQL.
"""

from collections.abc import AsyncIterator, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.commercial.public_api import EventInfo, EventStatus
from local_eventos.modules.staff.application.assignment_occupancy import AssignmentOccupancy
from local_eventos.modules.staff.application.errors import AssignmentOverlapError
from local_eventos.modules.staff.application.use_cases.get_staff_availability import (
    AvailabilityReport,
    GetStaffAvailability,
)
from local_eventos.modules.staff.application.use_cases.register_assignment import (
    RegisterAssignment,
)
from local_eventos.modules.staff.composition import worker_lookup
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import AssignmentAudit
from local_eventos.modules.staff.domain.availability_query import AvailabilityQuery
from local_eventos.modules.staff.domain.document import WorkerDocumentType
from local_eventos.modules.staff.domain.enums import AvailabilityState, WorkerFunction
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.assignment_conflict_lookup import (
    SqlAlchemyAssignmentConflictLookup,
)
from local_eventos.modules.staff.infrastructure.assignment_repository import (
    SqlAlchemyAssignmentRepository,
)
from local_eventos.modules.staff.infrastructure.clock import SystemClock
from local_eventos.modules.staff.infrastructure.mappers import worker_to_row
from local_eventos.modules.staff.infrastructure.orm_models import (
    StaffAssignmentAuditRow,
    StaffAssignmentRow,
)
from local_eventos.modules.staff.infrastructure.unavailability_repository import (
    SqlAlchemyUnavailabilityRepository,
)
from local_eventos.modules.staff.infrastructure.worker_repository import (
    SqlAlchemyWorkerRepository,
)
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_ACTOR = UUID("11111111-1111-1111-1111-111111111111")
_NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
# Ventana UTC (Lima 18:00–23:00) que ocupa la asignación sembrada de cada trabajador.
_START = datetime(2026, 12, 19, 23, 0, tzinfo=UTC)
_END = datetime(2026, 12, 20, 4, 0, tzinfo=UTC)
_EVENT_DATE = date(2026, 12, 19)
_EVENT_START = time(18, 0)
_EVENT_END = time(23, 0)

# Un trabajador y un evento por estado; el índice mantiene ids estables y legibles.
_STATUS_ORDER: tuple[EventStatus, ...] = (
    EventStatus.SCHEDULED,
    EventStatus.CONFIRMED,
    EventStatus.IN_PROGRESS,
    EventStatus.FINISHED,
    EventStatus.CANCELLED,
)
_WORKER_IDS: dict[EventStatus, UUID] = {
    status: UUID(f"22222222-2222-2222-2222-2222222222{index:02d}")
    for index, status in enumerate(_STATUS_ORDER)
}
_EVENT_IDS: dict[EventStatus, UUID] = {
    status: UUID(f"44444444-4444-4444-4444-4444444444{index:02d}")
    for index, status in enumerate(_STATUS_ORDER)
}
_OCCUPYING_STATUSES = frozenset(
    {
        EventStatus.SCHEDULED,
        EventStatus.CONFIRMED,
        EventStatus.IN_PROGRESS,
        EventStatus.FINISHED,
    }
)


@dataclass(frozen=True)
class _Window:
    """Ventana local de consulta y evento candidato `SCHEDULED` que la solapa."""

    label: str
    from_date: date
    to_date: date
    start_time: time | None
    end_time: time | None
    expected_statuses: frozenset[EventStatus]
    candidate_event_id: UUID
    candidate_date: date
    candidate_start: time
    candidate_end: time


_CANDIDATE_FULL = UUID("55555555-5555-5555-5555-555555555501")
_CANDIDATE_EXACT = UUID("55555555-5555-5555-5555-555555555502")
_CANDIDATE_EARLY = UUID("55555555-5555-5555-5555-555555555503")
_CANDIDATE_NEXT_DAY = UUID("55555555-5555-5555-5555-555555555504")

_WINDOWS: tuple[_Window, ...] = (
    _Window(
        label="dia-completo",
        from_date=date(2026, 12, 19),
        to_date=date(2026, 12, 19),
        start_time=None,
        end_time=None,
        expected_statuses=_OCCUPYING_STATUSES,
        candidate_event_id=_CANDIDATE_FULL,
        candidate_date=date(2026, 12, 19),
        candidate_start=time(18, 0),
        candidate_end=time(23, 0),
    ),
    _Window(
        label="ventana-exacta",
        from_date=date(2026, 12, 19),
        to_date=date(2026, 12, 19),
        start_time=time(18, 0),
        end_time=time(23, 0),
        expected_statuses=_OCCUPYING_STATUSES,
        candidate_event_id=_CANDIDATE_EXACT,
        candidate_date=date(2026, 12, 19),
        candidate_start=time(18, 0),
        candidate_end=time(23, 0),
    ),
    _Window(
        # Lima 12:00–13:00 = 17:00–18:00Z: contigua, no solapa (semiabierto).
        label="contigua",
        from_date=date(2026, 12, 19),
        to_date=date(2026, 12, 19),
        start_time=time(12, 0),
        end_time=time(13, 0),
        expected_statuses=frozenset(),
        candidate_event_id=_CANDIDATE_EARLY,
        candidate_date=date(2026, 12, 19),
        candidate_start=time(12, 0),
        candidate_end=time(13, 0),
    ),
    _Window(
        # La asignación termina a las 04:00Z del día 20; el día 20 está libre.
        label="dia-siguiente",
        from_date=date(2026, 12, 20),
        to_date=date(2026, 12, 20),
        start_time=None,
        end_time=None,
        expected_statuses=frozenset(),
        candidate_event_id=_CANDIDATE_NEXT_DAY,
        candidate_date=date(2026, 12, 20),
        candidate_start=time(12, 0),
        candidate_end=time(13, 0),
    ),
)

_Snapshot = tuple[tuple[tuple[UUID, bool, str], ...], int]


class FakeEventLookup:
    """Consulta de eventos en memoria con los datos de `EventInfo` (patrón de HU17)."""

    def __init__(self, events: dict[UUID, EventInfo] | None = None) -> None:
        self._events = events if events is not None else {}

    async def __call__(self, event_id: UUID) -> EventInfo | None:
        return self._events.get(event_id)


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("DATABASE_URL", url)
            command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        yield url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url)
    async with engine.begin() as connection:
        # TRUNCATE no dispara los triggers de fila append-only; deja todo vacío.
        await connection.execute(
            text(
                "TRUNCATE staff_unavailabilities_audit, staff_unavailabilities, "
                "staff_assignment_audit, staff_assignments, "
                "staff_worker_audit, staff_workers RESTART IDENTITY CASCADE"
            )
        )
    yield engine
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _event(
    event_id: UUID,
    status: EventStatus,
    *,
    code: str,
    event_date: date = _EVENT_DATE,
    start_time: time = _EVENT_START,
    end_time: time = _EVENT_END,
) -> EventInfo:
    return EventInfo(
        id=event_id,
        code=code,
        status=status,
        event_date=event_date,
        start_time=start_time,
        end_time=end_time,
    )


def _events() -> dict[UUID, EventInfo]:
    events = {
        _EVENT_IDS[status]: _event(_EVENT_IDS[status], status, code=f"EVT-2026-{index:04d}")
        for index, status in enumerate(_STATUS_ORDER)
    }
    for index, window in enumerate(_WINDOWS):
        events[window.candidate_event_id] = _event(
            window.candidate_event_id,
            EventStatus.SCHEDULED,
            code=f"CAND-2026-{index:04d}",
            event_date=window.candidate_date,
            start_time=window.candidate_start,
            end_time=window.candidate_end,
        )
    return events


def _created(assignment: Assignment) -> AssignmentAudit:
    return AssignmentAudit.created(
        assignment_id=assignment.id,
        actor_id=_ACTOR,
        occurred_at=_NOW,
    )


async def _seed_assignments(sessions: async_sessionmaker[AsyncSession]) -> FakeEventLookup:
    """Siembra un trabajador y una asignación activa por estado de evento."""
    async with sessions.begin() as session:
        repository = SqlAlchemyAssignmentRepository(session)
        for index, status in enumerate(_STATUS_ORDER):
            worker = Worker.register(
                name=f"Trabajador {status.value}",
                document_type=WorkerDocumentType.DNI,
                document_number=f"4412589{index}",
                phone=None,
                function=WorkerFunction.WAITER,
                rate=None,
                worker_id=_WORKER_IDS[status],
            )
            session.add(worker_to_row(worker))
            await session.flush()
            assignment = Assignment.register(
                event_id=_EVENT_IDS[status],
                worker_id=_WORKER_IDS[status],
                function=WorkerFunction.WAITER,
                start_at=_START,
                end_at=_END,
                pay=4500,
            )
            await repository.save(assignment, _created(assignment))
    return FakeEventLookup(_events())


async def _snapshot(sessions: async_sessionmaker[AsyncSession]) -> _Snapshot:
    async with sessions() as session:
        rows = (
            await session.execute(
                select(
                    StaffAssignmentRow.id,
                    StaffAssignmentRow.occupies,
                    StaffAssignmentRow.status,
                ).order_by(StaffAssignmentRow.id)
            )
        ).all()
        audits = await session.scalar(select(func.count()).select_from(StaffAssignmentAuditRow))
    stored = tuple((row[0], row[1], row[2]) for row in rows)
    return stored, int(audits or 0)


def _build_availability(session: AsyncSession, events: FakeEventLookup) -> GetStaffAvailability:
    """Cablea `GetStaffAvailability` (T-11) con los puertos reales y el doble de eventos."""
    return GetStaffAvailability(
        SqlAlchemyWorkerRepository(session),
        SqlAlchemyUnavailabilityRepository(session),
        SqlAlchemyAssignmentRepository(session),
        events,
        SqlAlchemyAssignmentConflictLookup(session),
    )


def _build_register(session: AsyncSession, events: FakeEventLookup) -> RegisterAssignment:
    assignments = SqlAlchemyAssignmentRepository(session)
    return RegisterAssignment(
        assignments,
        worker_lookup(session),
        events,
        AssignmentOccupancy(assignments, events),
        SystemClock(),
    )


def _query(window: _Window) -> AvailabilityQuery:
    return AvailabilityQuery(
        from_date=window.from_date,
        to_date=window.to_date,
        start_time=window.start_time,
        end_time=window.end_time,
    )


def _busy_workers(report: AvailabilityReport) -> set[UUID]:
    """Extrae el conjunto de trabajadores en `BUSY` del reporte de disponibilidad."""
    return {item.worker_id for item in report.items if item.state is AvailabilityState.BUSY}


def _expected_busy(window: _Window) -> set[UUID]:
    return {_WORKER_IDS[status] for status in window.expected_statuses}


async def _blocked_workers(
    sessions: async_sessionmaker[AsyncSession],
    events: FakeEventLookup,
    window: _Window,
    worker_ids: Iterable[UUID] | None = None,
) -> set[UUID]:
    """Trabajadores a los que HU17 responde 409 de solape para el candidato de la ventana."""
    blocked: set[UUID] = set()
    for worker_id in _WORKER_IDS.values() if worker_ids is None else worker_ids:
        async with sessions() as session:
            use_case = _build_register(session, events)
            try:
                await use_case.execute(
                    event_id=window.candidate_event_id,
                    worker_id=worker_id,
                    function=WorkerFunction.WAITER,
                    function_description=None,
                    date=window.candidate_date,
                    start_time=window.candidate_start,
                    end_time=window.candidate_end,
                    pay_cents=4500,
                    actor_id=_ACTOR,
                )
            except AssignmentOverlapError:
                blocked.add(worker_id)
            finally:
                # El alta solo se usa como sonda: nunca debe quedar escrita.
                await session.rollback()
    return blocked


@pytest.mark.integration
async def test_ca16_21_equivalencia_hu16_hu17(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    events = await _seed_assignments(sessions)
    before = await _snapshot(sessions)

    busy_by_window: dict[str, set[UUID]] = {}
    async with sessions() as session:
        availability = _build_availability(session, events)
        for window in _WINDOWS:
            report = await availability.execute(_query(window))
            busy_by_window[window.label] = _busy_workers(report)

    # HU16 es de solo lectura: ni `occupies`, ni filas, ni auditoría cambian.
    assert await _snapshot(sessions) == before

    for window in _WINDOWS:
        busy = busy_by_window[window.label]
        assert busy == _expected_busy(window), window.label
        # Mismo criterio efectivo que HU17: cancelado no ocupa, finalizado sí.
        assert await _blocked_workers(sessions, events, window) == busy, window.label

    # Los intentos sonda se revierten; el estado persistido sigue intacto.
    assert await _snapshot(sessions) == before


_ORPHAN_WORKER_ID = UUID("22222222-2222-2222-2222-222222222206")
_ORPHAN_EVENT_ID = UUID("44444444-4444-4444-4444-444444444406")


@pytest.mark.integration
async def test_ca16_21_orphan_event_is_busy_in_hu16_and_409_in_hu17(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Un evento inexistente no libera: HU16 marca BUSY y HU17 responde 409.

    `event_lookup` no conoce `_ORPHAN_EVENT_ID`; la asignación sigue ocupando en
    ambos caminos (HU17 no libera lo que no puede confirmar como cancelado).
    """
    async with sessions.begin() as session:
        worker = Worker.register(
            name="Trabajador Huérfano",
            document_type=WorkerDocumentType.DNI,
            document_number="44125899",
            phone=None,
            function=WorkerFunction.WAITER,
            rate=None,
            worker_id=_ORPHAN_WORKER_ID,
        )
        session.add(worker_to_row(worker))
        await session.flush()
        assignment = Assignment.register(
            event_id=_ORPHAN_EVENT_ID,
            worker_id=_ORPHAN_WORKER_ID,
            function=WorkerFunction.WAITER,
            start_at=_START,
            end_at=_END,
            pay=4500,
        )
        await SqlAlchemyAssignmentRepository(session).save(assignment, _created(assignment))

    events = FakeEventLookup(_events())
    window = _WINDOWS[0]

    async with sessions() as session:
        availability = _build_availability(session, events)
        report = await availability.execute(_query(window))

    assert _busy_workers(report) == {_ORPHAN_WORKER_ID}
    conflict = report.items[0].conflicts[0]
    assert conflict.event_code is None
    assert conflict.event_date is None
    assert conflict.start_time == time(18, 0)
    assert conflict.end_time == time(23, 0)
    assert await _blocked_workers(sessions, events, window, worker_ids=[_ORPHAN_WORKER_ID]) == {
        _ORPHAN_WORKER_ID
    }
