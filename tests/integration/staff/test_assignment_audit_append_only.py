"""Auditoría, inmutabilidad y borrado de asignaciones en PostgreSQL real (HU17, T-17).

Contra PostgreSQL con las migraciones de Alembic (plan §5.3/§5.5). Comprueba que el
trigger de auditoría rechaza `UPDATE`/`DELETE` pero admite inserciones, que una
asignación no se borra físicamente, que `worker_id`/`event_id` son inmutables y que
una asignación anulada no se reactiva. Además verifica que la asignación y su
auditoría se escriben de forma atómica: si la auditoría falla, la transacción no deja
ni una ni otra. Necesita Docker.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

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
    StaffAssignmentRow,
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
                "staff_worker_audit, staff_workers RESTART IDENTITY"
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
    number: str = "44125896",
) -> None:
    worker = Worker.register(
        name="Ana Pérez",
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
    assignment_id: UUID | None = None,
) -> Assignment:
    return Assignment.register(
        event_id=event_id,
        worker_id=worker_id,
        function=WorkerFunction.WAITER,
        start_at=_START,
        end_at=_END,
        pay=4500,
        assignment_id=assignment_id,
    )


def _created(assignment: Assignment) -> AssignmentAudit:
    return AssignmentAudit.created(
        assignment_id=assignment.id,
        actor_id=_ACTOR,
        occurred_at=_NOW,
    )


async def _save(assignment: Assignment, sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions.begin() as session:
        await _add_worker(session)
        await SqlAlchemyAssignmentRepository(session).save(assignment, _created(assignment))


async def _count(sessions: async_sessionmaker[AsyncSession], model: type[object]) -> int:
    async with sessions() as session:
        total = await session.scalar(select(func.count()).select_from(model))  # type: ignore[arg-type]
    return int(total or 0)


async def test_la_auditoria_rechaza_update_y_delete_pero_admite_insert(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    assignment = _assignment()
    await _save(assignment, sessions)

    # Una inserción válida (acción CANCELLED con motivo) sí se admite.
    async with sessions.begin() as session:
        await session.execute(
            text(
                "INSERT INTO staff_assignment_audit"
                " (assignment_id, action, reason, actor_id, occurred_at)"
                " VALUES (:assignment_id, 'CANCELLED', 'El cliente canceló', :actor, :now)"
            ),
            {
                "assignment_id": assignment.id,
                "actor": _ACTOR,
                "now": _NOW,
            },
        )

    assert await _count(sessions, StaffAssignmentAuditRow) == 2

    statements = [
        "UPDATE staff_assignment_audit SET reason = reason",
        "DELETE FROM staff_assignment_audit",
    ]
    for statement in statements:
        with pytest.raises(DBAPIError, match="no se modifica ni se borra"):
            async with sessions.begin() as session:
                await session.execute(text(statement))

    assert await _count(sessions, StaffAssignmentAuditRow) == 2


async def test_la_asignacion_no_se_borra_fisicamente(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    assignment = _assignment()
    await _save(assignment, sessions)

    with pytest.raises(DBAPIError, match="no se borra físicamente"):
        async with sessions.begin() as session:
            await session.execute(
                text("DELETE FROM staff_assignments WHERE id = :id"),
                {"id": assignment.id},
            )

    assert await _count(sessions, StaffAssignmentRow) == 1


async def test_las_claves_son_inmutables_y_los_campos_editables_no(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    assignment = _assignment()
    async with sessions.begin() as session:
        await _add_worker(session)
        await _add_worker(session, worker_id=_OTHER_WORKER_ID, number="76543210")
        await SqlAlchemyAssignmentRepository(session).save(assignment, _created(assignment))

    immutable = [
        (
            "UPDATE staff_assignments SET worker_id = :value WHERE id = :id",
            _OTHER_WORKER_ID,
        ),
        (
            "UPDATE staff_assignments SET event_id = :value WHERE id = :id",
            _OTHER_EVENT_ID,
        ),
    ]
    for statement, value in immutable:
        with pytest.raises(DBAPIError, match="claves de la asignación son inmutables"):
            async with sessions.begin() as session:
                await session.execute(text(statement), {"value": value, "id": assignment.id})

    # Un campo editable (el pago) sí se puede actualizar directamente.
    async with sessions.begin() as session:
        await session.execute(
            text("UPDATE staff_assignments SET pay_cents = 5000 WHERE id = :id"),
            {"id": assignment.id},
        )

    async with sessions() as session:
        row = await session.scalar(
            select(StaffAssignmentRow).where(StaffAssignmentRow.id == assignment.id)
        )

    assert row is not None
    assert row.worker_id == _WORKER_ID
    assert row.event_id == _EVENT_ID
    assert row.pay_cents == 5000


async def test_una_asignacion_anulada_no_se_reactiva(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    assignment = _assignment()
    await _save(assignment, sessions)

    async with sessions.begin() as session:
        await session.execute(
            text(
                "UPDATE staff_assignments SET status = 'CANCELLED', occupies = false WHERE id = :id"
            ),
            {"id": assignment.id},
        )

    with pytest.raises(DBAPIError, match="no se reactiva"):
        async with sessions.begin() as session:
            await session.execute(
                text("UPDATE staff_assignments SET status = 'ACTIVE' WHERE id = :id"),
                {"id": assignment.id},
            )

    async with sessions() as session:
        row = await session.scalar(
            select(StaffAssignmentRow).where(StaffAssignmentRow.id == assignment.id)
        )

    assert row is not None and row.status == AssignmentStatus.CANCELLED.value


async def test_rollback_si_falla_la_auditoria_no_deja_asignacion(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Prueba la atomicidad de la transacción, no un comportamiento de producción.

    La asignación y su auditoría se escriben en la misma transacción (plan §5.5). Si
    la auditoría viola un CHECK, el rollback debe deshacer también la asignación: no
    se modifica código de producción para forzarlo, se usa una auditoría inválida.
    """

    assignment = _assignment()

    with pytest.raises(IntegrityError, match="ck_staff_assignment_audit_reason_valid"):
        async with sessions() as session, session.begin():
            await _add_worker(session)
            await SqlAlchemyAssignmentRepository(session).save(assignment, _created(assignment))
            # `CREATED` con motivo viola ck_staff_assignment_audit_reason_valid.
            await session.execute(
                text(
                    "INSERT INTO staff_assignment_audit"
                    " (assignment_id, action, reason, actor_id, occurred_at)"
                    " VALUES (:assignment_id, 'CREATED', 'Motivo indebido', :actor, :now)"
                ),
                {
                    "assignment_id": assignment.id,
                    "actor": _ACTOR,
                    "now": _NOW,
                },
            )

    assert await _count(sessions, StaffAssignmentRow) == 0
    assert await _count(sessions, StaffAssignmentAuditRow) == 0
    # El trabajador se insertó en la misma transacción y también se revierte.
    assert await _count(sessions, StaffWorkerRow) == 0
