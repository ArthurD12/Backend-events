"""Constraints de asistencia y auditoría contra PostgreSQL real (HU18, T-07).

Cubre R-ATT-7/R-ATT-22 y CA-18.11 a nivel de base de datos: la PK de
`staff_attendance` garantiza un solo estado vigente por asignación, los CHECK
rechazan estados fuera de `ATTENDED`/`NOT_ATTENDED` y la auditoría exige motivo
recortado de 1..500 solo en las correcciones. Se inserta con SQL directo para
probar que la garantía la impone PostgreSQL y no la aplicación.

Las tablas se crean con las migraciones de Alembic, igual que en producción.
Necesita Docker/PostgreSQL.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
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
    VALUES (:assignment_id, :status, :recorded_by, :recorded_at)
    """
)
_INSERT_AUDIT = text(
    """
    INSERT INTO staff_attendance_audit (
        assignment_id, action, previous_status, new_status, reason, actor_id, occurred_at
    ) VALUES (
        :assignment_id, :action, :previous_status, :new_status, :reason, :actor_id, :occurred_at
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


async def _seed_assignment(session: AsyncSession) -> None:
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


def _attendance_params(*, status: str = "ATTENDED") -> dict[str, object]:
    return {
        "assignment_id": _ASSIGNMENT_ID,
        "status": status,
        "recorded_by": _ACTOR,
        "recorded_at": _NOW,
    }


def _audit_params(
    *,
    action: str = "RECORDED",
    previous_status: str | None = None,
    new_status: str = "ATTENDED",
    reason: str | None = None,
) -> dict[str, object]:
    return {
        "assignment_id": _ASSIGNMENT_ID,
        "action": action,
        "previous_status": previous_status,
        "new_status": new_status,
        "reason": reason,
        "actor_id": _ACTOR,
        "occurred_at": _NOW,
    }


async def _count(sessions: async_sessionmaker[AsyncSession], model: type[object]) -> int:
    async with sessions() as session:
        total = await session.scalar(select(func.count()).select_from(model))  # type: ignore[arg-type]
    return int(total or 0)


def _sqlstate(error: IntegrityError) -> str | None:
    orig: object = error.orig
    for candidate in (orig, getattr(orig, "orig", None)):
        value = getattr(candidate, "sqlstate", None)
        if isinstance(value, str):
            return value
    return None


def _constraint_name(error: IntegrityError) -> str | None:
    orig: object = error.orig
    for candidate in (orig, getattr(orig, "orig", None)):
        value = getattr(candidate, "constraint_name", None)
        if isinstance(value, str):
            return value
    return None


async def test_pk_unica_por_asignacion(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        await _seed_assignment(session)
        await session.execute(_INSERT_ATTENDANCE, _attendance_params())

    with pytest.raises(IntegrityError) as excinfo:
        async with sessions.begin() as session:
            await session.execute(_INSERT_ATTENDANCE, _attendance_params(status="NOT_ATTENDED"))

    assert _sqlstate(excinfo.value) == "23505"
    assert _constraint_name(excinfo.value) == "pk_staff_attendance"
    assert await _count(sessions, StaffAttendanceRow) == 1


async def test_check_estado_vigente_rechaza_valor_invalido(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(IntegrityError) as excinfo:
        async with sessions.begin() as session:
            await _seed_assignment(session)
            await session.execute(_INSERT_ATTENDANCE, _attendance_params(status="PENDING"))

    assert _sqlstate(excinfo.value) == "23514"
    assert _constraint_name(excinfo.value) == "ck_staff_attendance_status_valid"
    assert await _count(sessions, StaffAttendanceRow) == 0


async def test_check_auditoria_rechaza_new_status_invalido(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(IntegrityError) as excinfo:
        async with sessions.begin() as session:
            await _seed_assignment(session)
            await session.execute(_INSERT_AUDIT, _audit_params(new_status="MAYBE"))

    assert _constraint_name(excinfo.value) == "ck_staff_attendance_audit_new_status_valid"
    assert await _count(sessions, StaffAttendanceAuditRow) == 0


async def test_correccion_sin_motivo_rechazada(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(IntegrityError) as excinfo:
        async with sessions.begin() as session:
            await _seed_assignment(session)
            await session.execute(
                _INSERT_AUDIT,
                _audit_params(
                    action="CORRECTED",
                    previous_status="ATTENDED",
                    new_status="NOT_ATTENDED",
                    reason=None,
                ),
            )

    assert _sqlstate(excinfo.value) == "23514"
    assert _constraint_name(excinfo.value) == "ck_staff_attendance_audit_reason_and_status_valid"
    assert await _count(sessions, StaffAttendanceAuditRow) == 0


async def test_motivo_mayor_a_500_rechazado(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(IntegrityError) as excinfo:
        async with sessions.begin() as session:
            await _seed_assignment(session)
            await session.execute(
                _INSERT_AUDIT,
                _audit_params(
                    action="CORRECTED",
                    previous_status="ATTENDED",
                    new_status="NOT_ATTENDED",
                    reason="x" * 501,
                ),
            )

    assert _sqlstate(excinfo.value) == "23514"
    assert _constraint_name(excinfo.value) == "ck_staff_attendance_audit_reason_and_status_valid"
    assert await _count(sessions, StaffAttendanceAuditRow) == 0


async def test_correccion_con_mismo_estado_rechazada(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(IntegrityError) as excinfo:
        async with sessions.begin() as session:
            await _seed_assignment(session)
            await session.execute(
                _INSERT_AUDIT,
                _audit_params(
                    action="CORRECTED",
                    previous_status="ATTENDED",
                    new_status="ATTENDED",
                    reason="Motivo válido",
                ),
            )

    assert _constraint_name(excinfo.value) == ("ck_staff_attendance_audit_reason_and_status_valid")


async def test_primer_registro_sin_motivo_aceptado(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        await _seed_assignment(session)
        await session.execute(_INSERT_ATTENDANCE, _attendance_params())
        await session.execute(_INSERT_AUDIT, _audit_params())

    assert await _count(sessions, StaffAttendanceRow) == 1
    assert await _count(sessions, StaffAttendanceAuditRow) == 1
