"""Concurrencia real de las correcciones de asistencia (HU18, T-08). Necesita Docker.

Cubre R-ATT-7/R-ATT-8 y el plan §5.3: `lock_assignment` bloquea la fila de
`staff_assignments` con `SELECT ... FOR UPDATE`, de modo que dos correcciones
simultáneas sobre la misma asignación se serializan, ambas quedan auditadas y el
estado final es el de la última transacción confirmada.

Se usan dos sesiones y transacciones reales con `asyncio.Event` para forzar el solape
sin `sleep`: la primera mantiene el lock abierto mientras la segunda ya intenta
bloquearlo. Si desapareciera el `FOR UPDATE`, la segunda leería el estado anterior sin
esperar y no dejaría su auditoría, haciendo fallar las aserciones.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.staff.application.ports.attendance_repository import AttendanceView
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import AssignmentAudit
from local_eventos.modules.staff.domain.attendance import Attendance, AttendanceStatus
from local_eventos.modules.staff.domain.attendance_audit import AttendanceAction
from local_eventos.modules.staff.domain.document import WorkerDocumentType
from local_eventos.modules.staff.domain.enums import WorkerFunction
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.assignment_repository import (
    SqlAlchemyAssignmentRepository,
)
from local_eventos.modules.staff.infrastructure.attendance_orm_models import (
    StaffAttendanceAuditRow,
    StaffAttendanceRow,
)
from local_eventos.modules.staff.infrastructure.attendance_repository import (
    SqlAlchemyAttendanceRepository,
)
from local_eventos.modules.staff.infrastructure.mappers import worker_to_row
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_ACTOR = UUID("11111111-1111-1111-1111-111111111111")
_OTHER_ACTOR = UUID("99999999-9999-9999-9999-999999999999")
_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
_EVENT_ID = UUID("44444444-4444-4444-4444-444444444444")
_ASSIGNMENT_ID = UUID("aaaaaaaa-0000-0000-0000-000000000001")
_NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
_LATER = datetime(2026, 11, 26, 9, 30, tzinfo=UTC)
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


def _attendance_from_view(view: AttendanceView) -> Attendance:
    # `get` devuelve una vista inmutable; se reconstruye el agregado para corregir.
    return Attendance(
        assignment_id=view.assignment_id,
        status=view.status,
        recorded_by=view.recorded_by,
        recorded_at=view.recorded_at,
    )


async def _seed_attended(sessions: async_sessionmaker[AsyncSession]) -> None:
    """Trabajador, asignación y asistencia previa `ATTENDED` (auditoría `RECORDED`)."""
    async with sessions.begin() as session:
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

        assignment = Assignment.register(
            event_id=_EVENT_ID,
            worker_id=_WORKER_ID,
            function=WorkerFunction.WAITER,
            start_at=_START,
            end_at=_END,
            pay=4500,
            assignment_id=_ASSIGNMENT_ID,
        )
        await SqlAlchemyAssignmentRepository(session).save(
            assignment,
            AssignmentAudit.created(
                assignment_id=assignment.id,
                actor_id=_ACTOR,
                occurred_at=_NOW,
            ),
        )
        attendance, audit = Attendance.record(
            assignment_id=_ASSIGNMENT_ID,
            status=AttendanceStatus.ATTENDED,
            actor_id=_ACTOR,
            recorded_at=_NOW,
        )
        await SqlAlchemyAttendanceRepository(session).save(attendance, audit)


async def test_dos_correcciones_simultaneas_se_serializan_y_auditan(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_attended(sessions)

    first_locked = asyncio.Event()
    second_started = asyncio.Event()
    release_first = asyncio.Event()

    async def first_correction() -> None:
        async with sessions() as session:
            repository = SqlAlchemyAttendanceRepository(session)
            assert await repository.lock_assignment(_ASSIGNMENT_ID) is not None
            view = await repository.get(_ASSIGNMENT_ID)
            assert view is not None
            attendance = _attendance_from_view(view)
            audit = attendance.correct(
                new_status=AttendanceStatus.NOT_ATTENDED,
                reason="primera corrección simultánea",
                actor_id=_ACTOR,
                occurred_at=_NOW,
            )
            assert audit is not None
            await repository.save(attendance, audit)
            # Mantiene el lock abierto hasta que la segunda intenta tomarlo.
            first_locked.set()
            await release_first.wait()
            await session.commit()

    async def second_correction() -> None:
        await second_started.wait()
        async with sessions() as session:
            repository = SqlAlchemyAttendanceRepository(session)
            # Bloquea hasta que la primera confirma: relee el estado ya corregido.
            assert await repository.lock_assignment(_ASSIGNMENT_ID) is not None
            view = await repository.get(_ASSIGNMENT_ID)
            assert view is not None
            attendance = _attendance_from_view(view)
            audit = attendance.correct(
                new_status=AttendanceStatus.ATTENDED,
                reason="segunda corrección simultánea",
                actor_id=_OTHER_ACTOR,
                occurred_at=_LATER,
            )
            assert audit is not None
            await repository.save(attendance, audit)
            await session.commit()

    first_task = asyncio.create_task(first_correction())
    await asyncio.wait_for(first_locked.wait(), timeout=10)
    second_started.set()
    second_task = asyncio.create_task(second_correction())
    # Cede el turno para que la segunda llegue al `SELECT ... FOR UPDATE`.
    await asyncio.sleep(0)
    release_first.set()
    await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=20)

    async with sessions() as session:
        stored = await session.get(StaffAttendanceRow, _ASSIGNMENT_ID)
        audits = (
            await session.scalars(
                select(StaffAttendanceAuditRow)
                .where(StaffAttendanceAuditRow.assignment_id == _ASSIGNMENT_ID)
                .order_by(StaffAttendanceAuditRow.id)
            )
        ).all()

    # El estado final es el de la última transacción confirmada.
    assert stored is not None
    assert stored.status == AttendanceStatus.ATTENDED.value
    assert stored.recorded_by == _OTHER_ACTOR

    # Ambas correcciones quedaron auditadas sobre el valor realmente vigente.
    assert [row.action for row in audits] == [
        AttendanceAction.RECORDED.value,
        AttendanceAction.CORRECTED.value,
        AttendanceAction.CORRECTED.value,
    ]
    _, first_audit, second_audit = audits
    assert first_audit.previous_status == AttendanceStatus.ATTENDED.value
    assert first_audit.new_status == AttendanceStatus.NOT_ATTENDED.value
    assert first_audit.reason == "primera corrección simultánea"
    assert second_audit.previous_status == AttendanceStatus.NOT_ATTENDED.value
    assert second_audit.new_status == AttendanceStatus.ATTENDED.value
    assert second_audit.reason == "segunda corrección simultánea"


async def test_for_update_bloquea_a_la_segunda_transaccion(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_attended(sessions)

    async with sessions() as holder:
        assert (
            await SqlAlchemyAttendanceRepository(holder).lock_assignment(_ASSIGNMENT_ID) is not None
        )
        async with sessions() as waiter:
            # Si `FOR UPDATE` no bloqueara, la consulta volvería antes del timeout.
            await waiter.execute(text("SET LOCAL statement_timeout = '250ms'"))
            with pytest.raises(DBAPIError):
                await SqlAlchemyAttendanceRepository(waiter).lock_assignment(_ASSIGNMENT_ID)
            await waiter.rollback()
        await holder.rollback()

    # Tras liberar el lock, una nueva transacción lo obtiene sin bloqueo.
    async with sessions() as session:
        assert (
            await SqlAlchemyAttendanceRepository(session).lock_assignment(_ASSIGNMENT_ID)
            is not None
        )
