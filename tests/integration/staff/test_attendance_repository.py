"""Repositorio de asistencia contra PostgreSQL real (HU18, T-08). Necesita Docker.

Las tablas se crean con las migraciones de Alembic, igual que en producción. Cubre el
round-trip del estado vigente y su auditoría (`RECORDED` y `CORRECTED` con motivo), el
historial con asignaciones `ACTIVE`/`CANCELLED` (una fila por asignación, orden
`start_at DESC`), el pago en céntimos de `PEN`, el trabajador inactivo, el filtro
`event_id` aplicado en SQL y que una fila con evento huérfano **no se descarta**
(CA-18.6, CA-18.13, CA-18.19, CA-18.21, CA-18.22; R-ATT-7/R-ATT-8).

El repositorio no resuelve el evento: `event_id` viaja como referencia y la conversión
a `null` de los campos del evento se cubre en el caso de uso/API (R-ATT-23).
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.staff.application.ports.attendance_repository import AttendanceView
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import AssignmentAudit
from local_eventos.modules.staff.domain.attendance import Attendance, AttendanceStatus
from local_eventos.modules.staff.domain.attendance_audit import AttendanceAction
from local_eventos.modules.staff.domain.document import WorkerDocumentType
from local_eventos.modules.staff.domain.enums import AssignmentStatus, WorkerFunction
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.assignment_repository import (
    SqlAlchemyAssignmentRepository,
)
from local_eventos.modules.staff.infrastructure.attendance_orm_models import (
    StaffAttendanceAuditRow,
)
from local_eventos.modules.staff.infrastructure.attendance_repository import (
    SqlAlchemyAttendanceRepository,
)
from local_eventos.modules.staff.infrastructure.mappers import worker_to_row
from local_eventos.modules.staff.infrastructure.orm_models import StaffAssignmentRow
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_ACTOR = UUID("11111111-1111-1111-1111-111111111111")
_OTHER_ACTOR = UUID("99999999-9999-9999-9999-999999999999")
_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
_OTHER_WORKER_ID = UUID("33333333-3333-3333-3333-333333333333")
_EVENT_ID = UUID("44444444-4444-4444-4444-444444444444")
_OTHER_EVENT_ID = UUID("55555555-5555-5555-5555-555555555555")
_ORPHAN_EVENT_ID = UUID("66666666-6666-6666-6666-666666666666")
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


async def _add_worker(
    session: AsyncSession,
    *,
    worker_id: UUID = _WORKER_ID,
    name: str = "Ana Pérez",
    number: str = "44125896",
    inactive: bool = False,
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
    if inactive:
        worker.deactivate()
    session.add(worker_to_row(worker))
    await session.flush()


async def _add_assignment(
    session: AsyncSession,
    *,
    assignment_id: UUID,
    worker_id: UUID = _WORKER_ID,
    event_id: UUID = _EVENT_ID,
    start_at: datetime = _START,
    end_at: datetime = _END,
    pay: int = 4500,
    cancelled: bool = False,
) -> Assignment:
    assignment = Assignment.register(
        event_id=event_id,
        worker_id=worker_id,
        function=WorkerFunction.WAITER,
        start_at=start_at,
        end_at=end_at,
        pay=pay,
        assignment_id=assignment_id,
    )
    if cancelled:
        assignment.cancel()
        audit = AssignmentAudit.cancelled(
            assignment_id=assignment.id,
            actor_id=_ACTOR,
            occurred_at=_NOW,
            reason="El cliente canceló el servicio",
        )
    else:
        audit = AssignmentAudit.created(
            assignment_id=assignment.id,
            actor_id=_ACTOR,
            occurred_at=_NOW,
        )
    await SqlAlchemyAssignmentRepository(session).save(assignment, audit)
    return assignment


async def _record_attendance(
    session: AsyncSession,
    *,
    assignment_id: UUID = _ASSIGNMENT_ID,
    status: AttendanceStatus = AttendanceStatus.ATTENDED,
    actor_id: UUID = _ACTOR,
    recorded_at: datetime = _NOW,
) -> None:
    attendance, audit = Attendance.record(
        assignment_id=assignment_id,
        status=status,
        actor_id=actor_id,
        recorded_at=recorded_at,
    )
    await SqlAlchemyAttendanceRepository(session).save(attendance, audit)


def _attendance_from_view(view: AttendanceView) -> Attendance:
    # `get` devuelve `AttendanceView`; se reconstruye el agregado para corregir.
    return Attendance(
        assignment_id=view.assignment_id,
        status=view.status,
        recorded_by=view.recorded_by,
        recorded_at=view.recorded_at,
    )


async def test_roundtrip_estado_y_auditoria_record_y_correct(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        await _add_worker(session)
        await _add_assignment(session, assignment_id=_ASSIGNMENT_ID)
        await _record_attendance(session)

    # El primer registro y su auditoría `RECORDED` quedan persistidos.
    async with sessions.begin() as session:
        repository = SqlAlchemyAttendanceRepository(session)
        stored = await repository.get(_ASSIGNMENT_ID)
        assert stored is not None
        assert stored.status is AttendanceStatus.ATTENDED
        assert stored.recorded_by == _ACTOR
        assert stored.recorded_at == _NOW

        current = _attendance_from_view(stored)
        audit = current.correct(
            new_status=AttendanceStatus.NOT_ATTENDED,
            reason="  Se registró por error; el trabajador sí asistió  ",
            actor_id=_OTHER_ACTOR,
            occurred_at=_LATER,
        )
        assert audit is not None
        await repository.save(current, audit)

    async with sessions() as session:
        repository = SqlAlchemyAttendanceRepository(session)
        stored = await repository.get(_ASSIGNMENT_ID)
        audits = (
            await session.scalars(
                select(StaffAttendanceAuditRow)
                .where(StaffAttendanceAuditRow.assignment_id == _ASSIGNMENT_ID)
                .order_by(StaffAttendanceAuditRow.id)
            )
        ).all()
        assignment_row = await session.get(StaffAssignmentRow, _ASSIGNMENT_ID)

    assert stored is not None
    assert stored.status is AttendanceStatus.NOT_ATTENDED
    assert stored.recorded_by == _OTHER_ACTOR
    assert stored.recorded_at == _LATER

    assert [row.action for row in audits] == [
        AttendanceAction.RECORDED.value,
        AttendanceAction.CORRECTED.value,
    ]
    recorded, corrected = audits
    assert recorded.previous_status is None
    assert recorded.new_status == AttendanceStatus.ATTENDED.value
    assert recorded.reason is None
    assert corrected.previous_status == AttendanceStatus.ATTENDED.value
    assert corrected.new_status == AttendanceStatus.NOT_ATTENDED.value
    assert corrected.reason == "Se registró por error; el trabajador sí asistió"
    assert corrected.actor_id == _OTHER_ACTOR
    assert corrected.occurred_at == _LATER

    # CA-18.19: la asistencia no altera función, horario, pago ni estado de la asignación.
    assert assignment_row is not None
    assert assignment_row.worker_function == WorkerFunction.WAITER.value
    assert assignment_row.start_at == _START
    assert assignment_row.end_at == _END
    assert assignment_row.pay_cents == 4500
    assert assignment_row.currency == "PEN"
    assert assignment_row.status == AssignmentStatus.ACTIVE.value


async def test_historial_activas_y_anuladas_orden_y_pago_en_centimos(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    old = UUID("aaaaaaaa-0000-0000-0000-000000000010")
    recent = UUID("aaaaaaaa-0000-0000-0000-000000000011")
    cancelled = UUID("aaaaaaaa-0000-0000-0000-000000000012")

    async with sessions.begin() as session:
        await _add_worker(session)
        await _add_assignment(
            session,
            assignment_id=old,
            event_id=_EVENT_ID,
            start_at=datetime(2026, 12, 1, 18, 0, tzinfo=UTC),
            end_at=datetime(2026, 12, 1, 23, 0, tzinfo=UTC),
        )
        await _add_assignment(
            session,
            assignment_id=recent,
            event_id=_OTHER_EVENT_ID,
            start_at=datetime(2026, 12, 20, 18, 0, tzinfo=UTC),
            end_at=datetime(2026, 12, 20, 23, 0, tzinfo=UTC),
        )
        await _add_assignment(
            session,
            assignment_id=cancelled,
            event_id=_EVENT_ID,
            start_at=datetime(2026, 12, 10, 18, 0, tzinfo=UTC),
            end_at=datetime(2026, 12, 10, 23, 0, tzinfo=UTC),
            cancelled=True,
        )
        await _record_attendance(session, assignment_id=old)

    async with sessions() as session:
        rows = await SqlAlchemyAttendanceRepository(session).list_history(_WORKER_ID)

    # Una fila por asignación, de la más reciente a la más antigua.
    assert [row.assignment_id for row in rows] == [recent, cancelled, old]
    by_id = {row.assignment_id: row for row in rows}

    assert by_id[old].attendance_status is AttendanceStatus.ATTENDED
    assert by_id[old].recorded_by == _ACTOR
    assert by_id[recent].attendance_status is None
    assert by_id[cancelled].assignment_status is AssignmentStatus.CANCELLED
    assert by_id[cancelled].attendance_status is None
    assert all(row.worker_name == "Ana Pérez" for row in rows)

    # CA-18.13: pago acordado entero en céntimos de PEN, sin recalcular.
    assert all(row.pay_cents == 4500 for row in rows)
    assert all(row.currency == "PEN" for row in rows)


async def test_historial_incluye_trabajador_inactivo(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        await _add_worker(session, inactive=True)
        await _add_assignment(session, assignment_id=_ASSIGNMENT_ID)
        await _record_attendance(session)

    async with sessions() as session:
        rows = await SqlAlchemyAttendanceRepository(session).list_history(_WORKER_ID)

    assert len(rows) == 1
    assert rows[0].worker_id == _WORKER_ID
    assert rows[0].attendance_status is AttendanceStatus.ATTENDED


async def test_historial_filtra_por_event_id_en_sql(
    sessions: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
) -> None:
    target = UUID("aaaaaaaa-0000-0000-0000-000000000020")
    other = UUID("aaaaaaaa-0000-0000-0000-000000000021")

    async with sessions.begin() as session:
        await _add_worker(session)
        await _add_assignment(
            session,
            assignment_id=target,
            event_id=_EVENT_ID,
            start_at=datetime(2026, 12, 5, 18, 0, tzinfo=UTC),
            end_at=datetime(2026, 12, 5, 23, 0, tzinfo=UTC),
        )
        await _add_assignment(
            session,
            assignment_id=other,
            event_id=_OTHER_EVENT_ID,
            start_at=datetime(2026, 12, 6, 18, 0, tzinfo=UTC),
            end_at=datetime(2026, 12, 6, 23, 0, tzinfo=UTC),
        )

    statements: list[str] = []

    def _capture(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _capture)
    try:
        async with sessions() as session:
            rows = await SqlAlchemyAttendanceRepository(session).list_history(
                _WORKER_ID, event_id=_EVENT_ID
            )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _capture)

    assert [row.assignment_id for row in rows] == [target]
    # El filtro se aplica en SQL, no descartando filas en memoria.
    history_sql = [
        statement
        for statement in statements
        if "staff_assignments" in statement and "staff_attendance" in statement
    ]
    assert history_sql
    assert any("event_id" in statement for statement in history_sql)


async def test_historial_no_descarta_evento_huerfano(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        await _add_worker(session)
        # `commercial` no conoce este evento: el repositorio no lo resuelve ni descarta.
        await _add_assignment(session, assignment_id=_ASSIGNMENT_ID, event_id=_ORPHAN_EVENT_ID)

    async with sessions() as session:
        rows = await SqlAlchemyAttendanceRepository(session).list_history(_WORKER_ID)

    assert len(rows) == 1
    assert rows[0].assignment_id == _ASSIGNMENT_ID
    assert rows[0].event_id == _ORPHAN_EVENT_ID
    assert rows[0].attendance_status is None


async def test_lock_assignment_inexistente_devuelve_none(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        locked = await SqlAlchemyAttendanceRepository(session).lock_assignment(_ASSIGNMENT_ID)

    assert locked is None


async def test_historial_sin_asignaciones_es_vacio(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        await _add_worker(session, worker_id=_OTHER_WORKER_ID, name="Luis Gómez", number="87654321")

    async with sessions() as session:
        rows = await SqlAlchemyAttendanceRepository(session).list_history(_OTHER_WORKER_ID)
        total = await session.scalar(select(func.count()).select_from(StaffAttendanceAuditRow))

    assert rows == []
    assert total == 0
