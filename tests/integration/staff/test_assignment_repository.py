"""Repositorio de asignaciones contra PostgreSQL real (HU17, T-15). Necesita Docker.

Las tablas se crean con las migraciones de Alembic, igual que en producción. Cubre el
round-trip con auditoría, listados, solapes, la restricción de exclusión (SQLSTATE
`23P01`), la liberación `occupies=false`, el bloqueo del trabajador y las consultas
que usa la baja del trabajador.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.staff.application.errors import AssignmentOverlapError
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentView,
)
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import AssignmentAudit
from local_eventos.modules.staff.domain.document import WorkerDocumentType
from local_eventos.modules.staff.domain.enums import AssignmentStatus, WorkerFunction
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.assignment_repository import (
    SqlAlchemyAssignmentRepository,
)
from local_eventos.modules.staff.infrastructure.mappers import worker_to_row
from local_eventos.modules.staff.infrastructure.orm_models import (
    StaffAssignmentAuditRow,
    StaffWorkerRow,
)
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_ACTOR = UUID("11111111-1111-1111-1111-111111111111")
_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
_OTHER_WORKER_ID = UUID("33333333-3333-3333-3333-333333333333")
_EVENT_ID = UUID("44444444-4444-4444-4444-444444444444")
_OTHER_EVENT_ID = UUID("55555555-5555-5555-5555-555555555555")
_NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
_START = datetime(2026, 12, 19, 18, 0, tzinfo=UTC)
_END = datetime(2026, 12, 19, 23, 0, tzinfo=UTC)


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


async def _add_worker(
    session: AsyncSession,
    *,
    name: str = "Ana Pérez",
    number: str = "44125896",
    worker_id: UUID = _WORKER_ID,
) -> None:
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


def _assignment(
    *,
    worker_id: UUID = _WORKER_ID,
    event_id: UUID = _EVENT_ID,
    start_at: datetime = _START,
    end_at: datetime = _END,
    pay: int = 4500,
    assignment_id: UUID | None = None,
) -> Assignment:
    return Assignment.register(
        event_id=event_id,
        worker_id=worker_id,
        function=WorkerFunction.WAITER,
        start_at=start_at,
        end_at=end_at,
        pay=pay,
        assignment_id=assignment_id,
    )


def _created(assignment: Assignment) -> AssignmentAudit:
    return AssignmentAudit.created(
        assignment_id=assignment.id,
        actor_id=_ACTOR,
        occurred_at=_NOW,
    )


def _cancelled(assignment: Assignment) -> AssignmentAudit:
    return AssignmentAudit.cancelled(
        assignment_id=assignment.id,
        actor_id=_ACTOR,
        occurred_at=_NOW,
        reason="El cliente canceló el servicio",
    )


async def test_round_trip_con_auditoria_y_utc(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    # Hora de Lima (UTC-5) a las 13:00 → 18:00 UTC.
    lima = timezone(timedelta(hours=-5))
    assignment = _assignment(
        start_at=datetime(2026, 12, 19, 13, 0, tzinfo=lima),
        end_at=datetime(2026, 12, 19, 18, 0, tzinfo=lima),
        pay=6000,
    )

    async with sessions.begin() as session:
        await _add_worker(session)
        await SqlAlchemyAssignmentRepository(session).save(assignment, _created(assignment))

    async with sessions() as session:
        repository = SqlAlchemyAssignmentRepository(session)
        saved = await repository.get(assignment.id)
        view = await repository.get_view(assignment.id)
        audits = (
            await session.scalars(
                select(StaffAssignmentAuditRow).where(
                    StaffAssignmentAuditRow.assignment_id == assignment.id
                )
            )
        ).all()

    assert saved is not None
    assert saved.id == assignment.id
    assert saved.pay.cents == 6000
    assert saved.pay.currency == "PEN"
    assert saved.start_at == _START
    assert saved.start_at.tzinfo is UTC
    assert saved.end_at == _END
    assert saved.status is AssignmentStatus.ACTIVE
    assert saved.occupies is True

    assert isinstance(view, AssignmentView)
    assert view.worker_name == "Ana Pérez"
    assert view.pay_cents == 6000
    assert view.event_code is None
    assert view.event_status is None

    assert [audit.action for audit in audits] == ["CREATED"]


async def test_list_by_event_solo_activas_y_ordenadas(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    earlier = _assignment(assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000001"))
    later = _assignment(
        start_at=datetime(2026, 12, 20, 20, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 21, 1, 0, tzinfo=UTC),
        assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000002"),
    )
    cancelled = _assignment(
        start_at=datetime(2026, 12, 19, 19, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 22, 0, tzinfo=UTC),
        assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000003"),
    )
    cancelled.cancel()

    async with sessions.begin() as session:
        await _add_worker(session)
        repository = SqlAlchemyAssignmentRepository(session)
        await repository.save(earlier, _created(earlier))
        await repository.save(later, _created(later))
        await repository.save(cancelled, _cancelled(cancelled))

    async with sessions() as session:
        views = await SqlAlchemyAssignmentRepository(session).list_by_event(_EVENT_ID)

    assert [view.id for view in views] == [earlier.id, later.id]
    assert all(view.status is AssignmentStatus.ACTIVE for view in views)


async def test_get_view_incluye_anulada_y_listado_no(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    assignment = _assignment()
    assignment.cancel()

    async with sessions.begin() as session:
        await _add_worker(session)
        await SqlAlchemyAssignmentRepository(session).save(assignment, _cancelled(assignment))

    async with sessions() as session:
        repository = SqlAlchemyAssignmentRepository(session)
        view = await repository.get_view(assignment.id)
        listed = await repository.list_by_event(_EVENT_ID)

    assert view is not None and view.status is AssignmentStatus.CANCELLED
    assert listed == []


async def test_list_active_overlaps_detecta_y_excluye(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    existing = _assignment()
    between_events = _assignment(
        event_id=_OTHER_EVENT_ID,
        start_at=datetime(2026, 12, 21, 18, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 21, 23, 0, tzinfo=UTC),
        assignment_id=UUID("bbbbbbbb-0000-0000-0000-000000000002"),
    )

    async with sessions.begin() as session:
        await _add_worker(session)
        repository = SqlAlchemyAssignmentRepository(session)
        await repository.save(existing, _created(existing))
        await repository.save(between_events, _created(between_events))

    async with sessions() as session:
        repository = SqlAlchemyAssignmentRepository(session)
        # Solape en el mismo evento: 22:00–02:00 cruza 18:00–23:00.
        overlaps = await repository.list_active_overlaps(
            _WORKER_ID,
            datetime(2026, 12, 19, 22, 0, tzinfo=UTC),
            datetime(2026, 12, 20, 2, 0, tzinfo=UTC),
        )
        # Excluyendo la propia asignación no hay solape.
        excluded = await repository.list_active_overlaps(
            _WORKER_ID,
            datetime(2026, 12, 19, 22, 0, tzinfo=UTC),
            datetime(2026, 12, 20, 2, 0, tzinfo=UTC),
            exclude_assignment_id=existing.id,
        )
        # Intervalo contiguo (empieza justo al terminar) no es solape.
        contiguous = await repository.list_active_overlaps(
            _WORKER_ID,
            _END,
            datetime(2026, 12, 20, 3, 0, tzinfo=UTC),
        )
        # Solape con la asignación de otro evento.
        other_event = await repository.list_active_overlaps(
            _WORKER_ID,
            datetime(2026, 12, 21, 22, 0, tzinfo=UTC),
            datetime(2026, 12, 22, 2, 0, tzinfo=UTC),
        )

    assert [overlap.id for overlap in overlaps] == [existing.id]
    assert excluded == []
    assert contiguous == []
    assert [overlap.id for overlap in other_event] == [between_events.id]
    assert other_event[0].event_id == _OTHER_EVENT_ID


async def test_restriccion_de_exclusion_y_liberacion(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    first = _assignment()
    second = _assignment(
        start_at=datetime(2026, 12, 19, 22, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 20, 2, 0, tzinfo=UTC),
        assignment_id=UUID("cccccccc-0000-0000-0000-000000000002"),
    )

    async with sessions.begin() as session:
        await _add_worker(session)
        await SqlAlchemyAssignmentRepository(session).save(first, _created(first))

    with pytest.raises(AssignmentOverlapError):
        async with sessions.begin() as session:
            await SqlAlchemyAssignmentRepository(session).save(second, _created(second))

    # Al liberar la primera, el hueco queda libre y la segunda se puede guardar.
    async with sessions.begin() as session:
        repository = SqlAlchemyAssignmentRepository(session)
        saved = await repository.get(first.id)
        assert saved is not None
        await repository.release([saved])

    async with sessions.begin() as session:
        await SqlAlchemyAssignmentRepository(session).save(second, _created(second))

    async with sessions() as session:
        stored = await SqlAlchemyAssignmentRepository(session).get(second.id)

    assert stored is not None and stored.id == second.id


async def test_has_active_ending_after_y_list_occupying(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    active = _assignment()
    cancelled = _assignment(
        start_at=datetime(2026, 12, 21, 18, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 21, 23, 0, tzinfo=UTC),
        assignment_id=UUID("dddddddd-0000-0000-0000-000000000002"),
    )
    cancelled.cancel()

    async with sessions.begin() as session:
        await _add_worker(session)
        repository = SqlAlchemyAssignmentRepository(session)
        await repository.save(active, _created(active))
        await repository.save(cancelled, _cancelled(cancelled))

    async with sessions() as session:
        repository = SqlAlchemyAssignmentRepository(session)
        ending_after_now = await repository.has_active_ending_after(_WORKER_ID, _NOW)
        ending_after_end = await repository.has_active_ending_after(_WORKER_ID, _END)
        occupying = await repository.list_occupying(_WORKER_ID)

    assert ending_after_now is True
    assert ending_after_end is False
    assert [assignment.id for assignment in occupying] == [active.id]


async def test_lock_worker_permite_seguir(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    assignment = _assignment()

    async with sessions.begin() as session:
        await _add_worker(session)
        repository = SqlAlchemyAssignmentRepository(session)
        await repository.lock_worker(_WORKER_ID)
        await repository.save(assignment, _created(assignment))

    async with sessions() as session:
        saved = await SqlAlchemyAssignmentRepository(session).get(assignment.id)

    assert saved is not None and saved.id == assignment.id


async def test_lock_worker_con_id_inexistente_no_falla(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        await SqlAlchemyAssignmentRepository(session).lock_worker(_OTHER_WORKER_ID)

    async with sessions() as session:
        exists = await session.scalar(
            select(StaffWorkerRow.id).where(StaffWorkerRow.id == _OTHER_WORKER_ID)
        )

    assert exists is None
