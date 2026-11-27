"""Consulta de disponibilidad de solo lectura contra PostgreSQL real (HU16, T-13).

Cubre CA-16.3, CA-16.5, CA-16.6, CA-16.15, CA-16.16 y CA-16.19 con los repositorios
reales y el doble en memoria de `commercial.public_api` que ya usan los tests de
asignaciones. Comprueba que repetir la consulta no cambia nada, que `occupies` y la
auditoría quedan intactos, que un evento `CANCELLED` no liberado no ocupa y uno
`FINISHED` sí, que el estado refleja altas/ediciones/anulaciones, que un trabajador
inactivo se excluye y que la reactivación conserva su historial. Necesita Docker.
"""

from collections.abc import AsyncIterator, Iterator
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
from local_eventos.modules.staff.application.use_cases.get_staff_availability import (
    AvailabilityItem,
    AvailabilityReport,
    GetStaffAvailability,
)
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import AssignmentAudit
from local_eventos.modules.staff.domain.audit import AuditAction, WorkerAudit
from local_eventos.modules.staff.domain.availability_query import AvailabilityQuery
from local_eventos.modules.staff.domain.document import WorkerDocumentType
from local_eventos.modules.staff.domain.enums import (
    AvailabilityState,
    UnavailabilityKind,
    UnavailabilityStatus,
    WorkerFunction,
)
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.unavailability_audit import (
    UnavailabilityAudit,
    UnavailabilitySnapshot,
)
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.assignment_conflict_lookup import (
    SqlAlchemyAssignmentConflictLookup,
)
from local_eventos.modules.staff.infrastructure.assignment_repository import (
    SqlAlchemyAssignmentRepository,
)
from local_eventos.modules.staff.infrastructure.mappers import worker_to_row
from local_eventos.modules.staff.infrastructure.orm_models import (
    StaffAssignmentAuditRow,
    StaffAssignmentRow,
    StaffUnavailabilityAuditRow,
    StaffUnavailabilityRow,
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
_NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)
# Ventana UTC (Lima 18:00–23:00) que ocupa la asignación sembrada.
_START = datetime(2026, 12, 19, 23, 0, tzinfo=UTC)
_END = datetime(2026, 12, 20, 4, 0, tzinfo=UTC)
_EVENT_DATE = date(2026, 12, 19)
_EVENT_START = time(18, 0)
_EVENT_END = time(23, 0)

_WORKER_ID = UUID("22222222-2222-2222-2222-222222222201")
_OTHER_WORKER_ID = UUID("22222222-2222-2222-2222-222222222202")
_EVENT_ID = UUID("44444444-4444-4444-4444-444444444401")
_FINISHED_EVENT_ID = UUID("44444444-4444-4444-4444-444444444402")
_CANCELLED_EVENT_ID = UUID("44444444-4444-4444-4444-444444444403")


@dataclass(frozen=True)
class _Snapshot:
    """Estado persistido que la consulta de disponibilidad no debe alterar."""

    assignments: tuple[tuple[UUID, bool, str], ...]
    unavailabilities: tuple[tuple[UUID, str], ...]
    assignment_audits: int
    unavailability_audits: int


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
) -> EventInfo:
    return EventInfo(
        id=event_id,
        code=code,
        status=status,
        event_date=_EVENT_DATE,
        start_time=_EVENT_START,
        end_time=_EVENT_END,
    )


def _events() -> dict[UUID, EventInfo]:
    return {
        _EVENT_ID: _event(_EVENT_ID, EventStatus.SCHEDULED, code="EVT-2026-0101"),
        _FINISHED_EVENT_ID: _event(_FINISHED_EVENT_ID, EventStatus.FINISHED, code="EVT-2026-0102"),
        _CANCELLED_EVENT_ID: _event(
            _CANCELLED_EVENT_ID, EventStatus.CANCELLED, code="EVT-2026-0103"
        ),
    }


async def _add_worker(
    session: AsyncSession,
    *,
    worker_id: UUID = _WORKER_ID,
    name: str = "Ana Pérez",
    number: str = "44125896",
) -> Worker:
    worker = Worker.register(
        name=name,
        document_type=WorkerDocumentType.DNI,
        document_number=number,
        phone=None,
        function=WorkerFunction.WAITER,
        rate=None,
        worker_id=worker_id,
    )
    session.add(worker_to_row(worker))
    await session.flush()
    return worker


def _assignment(
    *,
    worker_id: UUID = _WORKER_ID,
    event_id: UUID = _EVENT_ID,
) -> Assignment:
    return Assignment.register(
        event_id=event_id,
        worker_id=worker_id,
        function=WorkerFunction.WAITER,
        start_at=_START,
        end_at=_END,
        pay=4500,
    )


def _assignment_created(assignment: Assignment) -> AssignmentAudit:
    return AssignmentAudit.created(
        assignment_id=assignment.id,
        actor_id=_ACTOR,
        occurred_at=_NOW,
    )


def _worker_audit(worker: Worker, action: AuditAction, reason: str | None = None) -> WorkerAudit:
    return WorkerAudit(
        worker_id=worker.id,
        action=action,
        changed_by=_ACTOR,
        changed_at=_NOW,
        reason=reason,
    )


def _unavailability(
    *,
    unavailability_id: UUID | None = None,
    kind: UnavailabilityKind = UnavailabilityKind.VACATION,
    description: str | None = None,
    start_at: datetime = _START,
    end_at: datetime = _END,
) -> Unavailability:
    return Unavailability.register(
        worker_id=_WORKER_ID,
        kind=kind,
        description=description,
        start_at=start_at,
        end_at=end_at,
        unavailability_id=unavailability_id,
    )


def _created_account(unavailability: Unavailability) -> UnavailabilityAudit:
    return UnavailabilityAudit.created(
        unavailability_id=unavailability.id,
        actor_id=_ACTOR,
        occurred_at=_NOW,
    )


async def _save_assignment(session: AsyncSession, assignment: Assignment) -> None:
    await SqlAlchemyAssignmentRepository(session).save(assignment, _assignment_created(assignment))


async def _save_unavailability(session: AsyncSession, unavailability: Unavailability) -> None:
    await SqlAlchemyUnavailabilityRepository(session).save(
        unavailability, _created_account(unavailability)
    )


async def _snapshot(sessions: async_sessionmaker[AsyncSession]) -> _Snapshot:
    async with sessions() as session:
        assignments = (
            await session.execute(
                select(
                    StaffAssignmentRow.id,
                    StaffAssignmentRow.occupies,
                    StaffAssignmentRow.status,
                ).order_by(StaffAssignmentRow.id)
            )
        ).all()
        unavailabilities = (
            await session.execute(
                select(
                    StaffUnavailabilityRow.id,
                    StaffUnavailabilityRow.status,
                ).order_by(StaffUnavailabilityRow.id)
            )
        ).all()
        assignment_audits = await session.scalar(
            select(func.count()).select_from(StaffAssignmentAuditRow)
        )
        unavailability_audits = await session.scalar(
            select(func.count()).select_from(StaffUnavailabilityAuditRow)
        )
    return _Snapshot(
        assignments=tuple((row[0], row[1], row[2]) for row in assignments),
        unavailabilities=tuple((row[0], row[1]) for row in unavailabilities),
        assignment_audits=int(assignment_audits or 0),
        unavailability_audits=int(unavailability_audits or 0),
    )


def _build(session: AsyncSession, events: FakeEventLookup) -> GetStaffAvailability:
    """Cablea `GetStaffAvailability` con los puertos reales y el doble de eventos."""
    return GetStaffAvailability(
        SqlAlchemyWorkerRepository(session),
        SqlAlchemyUnavailabilityRepository(session),
        SqlAlchemyAssignmentRepository(session),
        events,
        SqlAlchemyAssignmentConflictLookup(session),
    )


def _query(*, from_date: date = _EVENT_DATE, to_date: date = _EVENT_DATE) -> AvailabilityQuery:
    return AvailabilityQuery(from_date=from_date, to_date=to_date)


def _by_worker(report: AvailabilityReport) -> dict[UUID, AvailabilityItem]:
    return {item.worker_id: item for item in report.items}


async def test_ca16_16_consulta_repetida_identica_sin_escribir(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    events = FakeEventLookup(_events())
    async with sessions.begin() as session:
        await _add_worker(session)
        await _save_assignment(session, _assignment())
        await _save_unavailability(session, _unavailability())
    before = await _snapshot(sessions)

    async with sessions() as session:
        use_case = _build(session, events)
        first = await use_case.execute(_query())
        second = await use_case.execute(_query())

    assert first == second
    assert len(first.items) == 1
    assert first.items[0].state is AvailabilityState.UNAVAILABLE
    # Ni `occupies`, ni filas, ni auditoría cambian (R-DIS-1, CA-16.16).
    assert await _snapshot(sessions) == before


async def test_ca16_15_cancelado_no_liberado_no_ocupa_y_finalizado_si(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    events = FakeEventLookup(_events())
    async with sessions.begin() as session:
        await _add_worker(session, worker_id=_WORKER_ID, name="Ana Pérez", number="44125896")
        await _add_worker(
            session,
            worker_id=_OTHER_WORKER_ID,
            name="Luis Gómez",
            number="44125897",
        )
        # El evento está cancelado y la asignación sigue ocupando: aún no se liberó.
        await _save_assignment(
            session, _assignment(worker_id=_WORKER_ID, event_id=_CANCELLED_EVENT_ID)
        )
        await _save_assignment(
            session, _assignment(worker_id=_OTHER_WORKER_ID, event_id=_FINISHED_EVENT_ID)
        )
    before = await _snapshot(sessions)

    async with sessions() as session:
        report = await _build(session, events).execute(_query())

    states = {worker_id: item.state for worker_id, item in _by_worker(report).items()}
    assert states[_WORKER_ID] is AvailabilityState.FREE
    assert states[_OTHER_WORKER_ID] is AvailabilityState.BUSY
    assert _by_worker(report)[_WORKER_ID].conflicts == ()
    assert len(_by_worker(report)[_OTHER_WORKER_ID].conflicts) == 1

    # El filtro es solo de lectura: la asignación cancelada sigue `occupies=true`.
    after = await _snapshot(sessions)
    assert after == before
    assert all(occupies for _, occupies, _ in after.assignments)


async def test_ca16_19_refleja_altas_ediciones_y_anulaciones(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    events = FakeEventLookup(_events())
    async with sessions.begin() as session:
        await _add_worker(session)

    async with sessions() as session:
        use_case = _build(session, events)
        assert (await use_case.execute(_query())).items[0].state is AvailabilityState.FREE

    unavailability = _unavailability()
    async with sessions.begin() as session:
        await _save_unavailability(session, unavailability)

    async with sessions() as session:
        item = (await _build(session, events).execute(_query())).items[0]
    assert item.state is AvailabilityState.UNAVAILABLE
    assert item.unavailabilities[0].kind is UnavailabilityKind.VACATION

    previous = UnavailabilitySnapshot.from_mapping(unavailability.snapshot())
    unavailability.update(
        kind=UnavailabilityKind.OTHER,
        description="Trámite personal",
        start_at=_START,
        end_at=_END,
    )
    new = UnavailabilitySnapshot.from_mapping(unavailability.snapshot())
    async with sessions.begin() as session:
        await SqlAlchemyUnavailabilityRepository(session).save(
            unavailability,
            UnavailabilityAudit.updated(
                unavailability_id=unavailability.id,
                actor_id=_ACTOR,
                occurred_at=_NOW,
                reason="Se precisó el motivo",
                previous_values=previous,
                new_values=new,
            ),
        )

    async with sessions() as session:
        item = (await _build(session, events).execute(_query())).items[0]
    assert item.state is AvailabilityState.UNAVAILABLE
    assert item.unavailabilities[0].kind is UnavailabilityKind.OTHER
    assert item.unavailabilities[0].description == "Trámite personal"

    unavailability.cancel()
    async with sessions.begin() as session:
        await SqlAlchemyUnavailabilityRepository(session).save(
            unavailability,
            UnavailabilityAudit.cancelled(
                unavailability_id=unavailability.id,
                actor_id=_ACTOR,
                occurred_at=_NOW,
                reason="Se reprogramó el trámite",
            ),
        )

    async with sessions() as session:
        assert (await _build(session, events).execute(_query())).items[0].state is (
            AvailabilityState.FREE
        )

    async with sessions() as session:
        actions = (
            await session.scalars(
                select(StaffUnavailabilityAuditRow.action)
                .where(StaffUnavailabilityAuditRow.unavailability_id == unavailability.id)
                .order_by(StaffUnavailabilityAuditRow.id)
            )
        ).all()
        stored = await session.get(StaffUnavailabilityRow, unavailability.id)
    assert actions == ["CREATED", "UPDATED", "CANCELLED"]
    assert stored is not None and stored.status == UnavailabilityStatus.CANCELLED.value


async def test_ca16_5_ca16_6_inactivo_excluido_y_reactivacion_conserva_historial(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    events = FakeEventLookup(_events())
    async with sessions.begin() as session:
        worker = await _add_worker(session)
        await _save_unavailability(session, _unavailability())
    before = await _snapshot(sessions)

    async with sessions() as session:
        item = (await _build(session, events).execute(_query())).items[0]
    assert item.state is AvailabilityState.UNAVAILABLE

    worker.deactivate()
    async with sessions.begin() as session:
        await SqlAlchemyWorkerRepository(session).save(
            worker, _worker_audit(worker, AuditAction.DEACTIVATED, "Baja temporal")
        )

    async with sessions() as session:
        assert (await _build(session, events).execute(_query())).items == []
    # CA-16.5: inactivo excluido; su indisponibilidad no se borra.
    assert await _snapshot(sessions) == before

    worker.activate()
    async with sessions.begin() as session:
        await SqlAlchemyWorkerRepository(session).save(
            worker, _worker_audit(worker, AuditAction.ACTIVATED, "Reincorporación")
        )

    async with sessions() as session:
        item = (await _build(session, events).execute(_query())).items[0]
    # CA-16.6: al reactivarse vuelve a la consulta con el mismo historial.
    assert item.state is AvailabilityState.UNAVAILABLE
    assert item.unavailabilities[0].kind is UnavailabilityKind.VACATION
    assert await _snapshot(sessions) == before


async def test_ca16_3_estado_en_tiempo_real_por_ventana(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    events = FakeEventLookup(_events())
    async with sessions.begin() as session:
        await _add_worker(session)
        await _save_assignment(session, _assignment())

    async with sessions() as session:
        use_case = _build(session, events)
        busy = await use_case.execute(_query())
        free = await use_case.execute(
            _query(from_date=date(2026, 12, 20), to_date=date(2026, 12, 20))
        )

    assert _by_worker(busy)[_WORKER_ID].state is AvailabilityState.BUSY
    # La asignación termina a las 04:00Z del día 20; el día 20 está libre.
    assert _by_worker(free)[_WORKER_ID].state is AvailabilityState.FREE
