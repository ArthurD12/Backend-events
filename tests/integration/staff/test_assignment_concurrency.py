"""Concurrencia real del no-solape de asignaciones (HU17, CA-17.11, T-16).

Dos sesiones independientes intentan asignar al mismo trabajador en ventanas que se
superponen. Ninguna toma `lock_worker`: se quiere probar la restricción de exclusión
de PostgreSQL, no la serialización por bloqueo. Exactamente una transacción gana y
la otra recibe `AssignmentOverlapError`; la base queda con una sola fila (plan §5.5).

Las tablas se crean con las migraciones de Alembic. Necesita Docker/PostgreSQL.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.staff.application.errors import AssignmentOverlapError
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import AssignmentAudit
from local_eventos.modules.staff.domain.document import WorkerDocumentType
from local_eventos.modules.staff.domain.enums import WorkerFunction
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.assignment_repository import (
    SqlAlchemyAssignmentRepository,
)
from local_eventos.modules.staff.infrastructure.mappers import worker_to_row
from local_eventos.modules.staff.infrastructure.orm_models import StaffAssignmentRow
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_ACTOR = UUID("11111111-1111-1111-1111-111111111111")
_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
_EVENT_ID = UUID("44444444-4444-4444-4444-444444444444")
_NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


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
                "TRUNCATE staff_assignment_audit, staff_assignments, "
                "staff_worker_audit, staff_workers RESTART IDENTITY CASCADE"
            )
        )
    yield engine
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _add_worker(session: AsyncSession) -> None:
    worker = Worker.register(
        name="Ana Pérez",
        document_type=WorkerDocumentType.DNI,
        document_number="44125896",
        phone=None,
        function=WorkerFunction.WAITER,
        rate=None,
        worker_id=_WORKER_ID,
    )
    session.add(worker_to_row(worker))
    await session.flush()


def _assignment(
    *,
    start_at: datetime,
    end_at: datetime,
    assignment_id: UUID,
) -> Assignment:
    return Assignment.register(
        event_id=_EVENT_ID,
        worker_id=_WORKER_ID,
        function=WorkerFunction.WAITER,
        start_at=start_at,
        end_at=end_at,
        pay=4500,
        assignment_id=assignment_id,
    )


def _created(assignment: Assignment) -> AssignmentAudit:
    return AssignmentAudit.created(
        assignment_id=assignment.id,
        actor_id=_ACTOR,
        occurred_at=_NOW,
    )


async def test_ca17_11_dos_transacciones_simultaneas_dejan_una_sola(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    first = _assignment(
        start_at=datetime(2026, 12, 19, 18, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 23, 0, tzinfo=UTC),
        assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000001"),
    )
    second = _assignment(
        start_at=datetime(2026, 12, 19, 22, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 20, 2, 0, tzinfo=UTC),
        assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000002"),
    )

    async with sessions.begin() as session:
        await _add_worker(session)

    async def attempt(assignment: Assignment) -> str:
        # Sin `lock_worker`: la restricción de exclusión es quien decide.
        async with sessions() as session:
            try:
                await SqlAlchemyAssignmentRepository(session).save(assignment, _created(assignment))
                await session.commit()
                return "ok"
            except AssignmentOverlapError:
                await session.rollback()
                return "solape"

    results = await asyncio.gather(attempt(first), attempt(second))

    async with sessions() as session:
        total = await session.scalar(select(func.count()).select_from(StaffAssignmentRow))
        stored = (await session.scalars(select(StaffAssignmentRow.id))).all()

    assert sorted(results) == ["ok", "solape"]
    assert total == 1
    assert len(stored) == 1
    assert stored[0] in {first.id, second.id}
