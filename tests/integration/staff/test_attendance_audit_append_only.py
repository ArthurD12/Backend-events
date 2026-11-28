"""Auditoría append-only y borrado de asistencia en PostgreSQL real (HU18, T-07).

Contra PostgreSQL con las migraciones de Alembic. Comprueba que el trigger
`BEFORE UPDATE OR DELETE` de `staff_attendance_audit` rechaza la modificación y
el borrado, que `staff_attendance` no se borra físicamente (R-ATT-7) y que las
inserciones válidas siguen admitiéndose. Necesita Docker.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.staff.infrastructure.attendance_orm_models import (
    StaffAttendanceAuditRow,
    StaffAttendanceRow,
)
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_ACTOR = UUID("11111111-1111-1111-1111-111111111111")
_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
_EVENT_ID = UUID("44444444-4444-4444-4444-444444444444")
_ASSIGNMENT_ID = UUID("aaaaaaaa-0000-0000-0000-000000000001")
_NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)

_INSERT_WORKER = text(
    """
    INSERT INTO staff_workers (id, name, document_type, document_number, status)
    VALUES (:id, 'Ana Pérez', 'DNI', '44125896', 'ACTIVE')
    """
)
_INSERT_ASSIGNMENT = text(
    """
    INSERT INTO staff_assignments (
        id, event_id, worker_id, worker_function, function_description,
        start_at, end_at, pay_cents, currency, status, occupies
    ) VALUES (
        :id, :event_id, :worker_id, 'WAITER', NULL,
        :start_at, :end_at, 4500, 'PEN', 'ACTIVE', true
    )
    """
)
_INSERT_ATTENDANCE = text(
    """
    INSERT INTO staff_attendance (assignment_id, status, recorded_by, recorded_at)
    VALUES (:assignment_id, 'ATTENDED', :recorded_by, :recorded_at)
    """
)
_INSERT_AUDIT = text(
    """
    INSERT INTO staff_attendance_audit (
        assignment_id, action, previous_status, new_status, reason, actor_id, occurred_at
    ) VALUES (
        :assignment_id, 'RECORDED', NULL, 'ATTENDED', NULL, :actor_id, :occurred_at
    )
    """
)


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
                "TRUNCATE staff_attendance_audit, staff_attendance, "
                "staff_unavailabilities_audit, staff_unavailabilities, "
                "staff_assignment_audit, staff_assignments, "
                "staff_worker_audit, staff_workers RESTART IDENTITY CASCADE"
            )
        )
    yield engine
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions.begin() as session:
        await session.execute(_INSERT_WORKER, {"id": _WORKER_ID})
        await session.execute(
            _INSERT_ASSIGNMENT,
            {
                "id": _ASSIGNMENT_ID,
                "event_id": _EVENT_ID,
                "worker_id": _WORKER_ID,
                "start_at": datetime(2026, 12, 19, 18, 0, tzinfo=UTC),
                "end_at": datetime(2026, 12, 19, 23, 0, tzinfo=UTC),
            },
        )
        await session.execute(
            _INSERT_ATTENDANCE,
            {
                "assignment_id": _ASSIGNMENT_ID,
                "recorded_by": _ACTOR,
                "recorded_at": _NOW,
            },
        )
        await session.execute(
            _INSERT_AUDIT,
            {
                "assignment_id": _ASSIGNMENT_ID,
                "actor_id": _ACTOR,
                "occurred_at": _NOW,
            },
        )


async def _count(sessions: async_sessionmaker[AsyncSession], model: type[object]) -> int:
    async with sessions() as session:
        total = await session.scalar(select(func.count()).select_from(model))  # type: ignore[arg-type]
    return int(total or 0)


async def test_la_auditoria_rechaza_update_y_delete_pero_admite_insert(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(sessions)

    # Una inserción válida (CORRECTED con motivo) sí se admite.
    async with sessions.begin() as session:
        await session.execute(
            text(
                "INSERT INTO staff_attendance_audit"
                " (assignment_id, action, previous_status, new_status, reason,"
                " actor_id, occurred_at)"
                " VALUES (:assignment_id, 'CORRECTED', 'ATTENDED', 'NOT_ATTENDED',"
                " 'No se presentó', :actor, :now)"
            ),
            {"assignment_id": _ASSIGNMENT_ID, "actor": _ACTOR, "now": _NOW},
        )

    assert await _count(sessions, StaffAttendanceAuditRow) == 2

    statements = [
        "UPDATE staff_attendance_audit SET reason = reason",
        "DELETE FROM staff_attendance_audit",
    ]
    for statement in statements:
        with pytest.raises(DBAPIError, match="no se modifica ni se borra"):
            async with sessions.begin() as session:
                await session.execute(text(statement))

    assert await _count(sessions, StaffAttendanceAuditRow) == 2


async def test_la_asistencia_no_se_borra_fisicamente(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(sessions)

    with pytest.raises(DBAPIError, match="no se borra físicamente"):
        async with sessions.begin() as session:
            await session.execute(
                text("DELETE FROM staff_attendance WHERE assignment_id = :id"),
                {"id": _ASSIGNMENT_ID},
            )

    assert await _count(sessions, StaffAttendanceRow) == 1
