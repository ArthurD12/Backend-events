"""Auditoría del personal de solo inserción (HU15, RN03, plan §4/§6.2, T-13).

Contra PostgreSQL real con las migraciones de Alembic: el trigger rechaza `UPDATE`
y `DELETE` directos sobre `staff_worker_audit`, las cuatro operaciones (alta,
edición, baja y reactivación) escriben exactamente la fila esperada y el CHECK de
la base solo admite `reason` en `ACTIVATED`/`DEACTIVATED`. Necesita Docker.
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

from local_eventos.modules.staff.application.use_cases.change_worker_status import (
    ActivateWorker,
    DeactivateWorker,
)
from local_eventos.modules.staff.application.use_cases.register_worker import (
    RegisterWorker,
)
from local_eventos.modules.staff.application.use_cases.update_worker import (
    UpdateWorker,
)
from local_eventos.modules.staff.application.use_cases.worker_data import WorkerData
from local_eventos.modules.staff.domain.document import DocumentType
from local_eventos.modules.staff.domain.enums import WorkerFunction, WorkerType
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.infrastructure.orm_models import StaffWorkerAuditRow
from local_eventos.modules.staff.infrastructure.worker_repository import (
    SqlAlchemyWorkerRepository,
)
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_CREATOR = UUID("11111111-1111-1111-1111-111111111111")
_EDITOR = UUID("22222222-2222-2222-2222-222222222222")
_CREATED_AT = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)
_UPDATED_AT = datetime(2026, 11, 24, 10, 0, tzinfo=UTC)
_DEACTIVATED_AT = datetime(2026, 11, 24, 11, 0, tzinfo=UTC)
_ACTIVATED_AT = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


class _SequenceClock:
    """Reloj determinista: devuelve los instantes en el orden en que se auditan."""

    def __init__(self, *moments: datetime) -> None:
        self._moments = list(moments)

    def now(self) -> datetime:
        return self._moments.pop(0)


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
        # TRUNCATE no dispara el trigger de fila append-only; deja las tablas vacías.
        await connection.execute(
            text("TRUNCATE staff_worker_audit, staff_workers RESTART IDENTITY")
        )
    yield engine
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _data(
    *,
    name: str = "José Ramírez Quispe",
    number: str = "44125896",
    phone: str | None = "987654321",
) -> WorkerData:
    return WorkerData(
        name=name,
        document_type=DocumentType.DNI,
        document_number=number,
        phone=phone,
        function=WorkerFunction.COOK,
        worker_type=WorkerType.FIXED,
        rate=Money(15000),
    )


async def _registered_worker(
    sessions: async_sessionmaker[AsyncSession],
) -> UUID:
    clock = _SequenceClock(_CREATED_AT)
    async with sessions.begin() as session:
        worker = await RegisterWorker(
            SqlAlchemyWorkerRepository(session), clock
        ).execute(_data(), _CREATOR)
    return worker.id


async def test_hu15_el_trigger_rechaza_update_y_delete_directos(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker_id = await _registered_worker(sessions)

    statements = [
        "UPDATE staff_worker_audit SET changed_at = changed_at",
        "DELETE FROM staff_worker_audit",
    ]

    for statement in statements:
        with pytest.raises(DBAPIError, match="no se modifica ni se borra"):
            async with sessions.begin() as session:
                await session.execute(text(statement))

    async with sessions() as session:
        total = await session.scalar(select(func.count()).select_from(StaffWorkerAuditRow))
        row = await session.scalar(select(StaffWorkerAuditRow))

    assert total == 1
    assert row is not None and row.worker_id == worker_id
    assert row.action == "CREATED" and row.reason is None


async def test_hu15_las_cuatro_operaciones_escriben_su_fila_de_auditoria(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    clock = _SequenceClock(_CREATED_AT, _UPDATED_AT, _DEACTIVATED_AT, _ACTIVATED_AT)

    async with sessions.begin() as session:
        worker = await RegisterWorker(
            SqlAlchemyWorkerRepository(session), clock
        ).execute(_data(), _CREATOR)

    async with sessions.begin() as session:
        await UpdateWorker(SqlAlchemyWorkerRepository(session), clock).execute(
            worker.id,
            _data(name="José Ramírez", phone="912345678"),
            _EDITOR,
        )

    async with sessions.begin() as session:
        await DeactivateWorker(SqlAlchemyWorkerRepository(session), clock).execute(
            worker.id, "Renuncia", _CREATOR
        )

    async with sessions.begin() as session:
        await ActivateWorker(SqlAlchemyWorkerRepository(session), clock).execute(
            worker.id, "Reingreso", _EDITOR
        )

    async with sessions() as session:
        rows = (
            await session.scalars(select(StaffWorkerAuditRow).order_by(StaffWorkerAuditRow.id))
        ).all()

    assert [
        (row.worker_id, row.action, row.changed_by, row.changed_at, row.reason)
        for row in rows
    ] == [
        (worker.id, "CREATED", _CREATOR, _CREATED_AT, None),
        (worker.id, "UPDATED", _EDITOR, _UPDATED_AT, None),
        (worker.id, "DEACTIVATED", _CREATOR, _DEACTIVATED_AT, "Renuncia"),
        (worker.id, "ACTIVATED", _EDITOR, _ACTIVATED_AT, "Reingreso"),
    ]


@pytest.mark.parametrize("action", ["CREATED", "UPDATED"])
async def test_hu15_el_check_rechaza_reason_fuera_de_cambios_de_estado(
    sessions: async_sessionmaker[AsyncSession], action: str
) -> None:
    worker_id = await _registered_worker(sessions)

    with pytest.raises(IntegrityError, match="ck_staff_worker_audit_reason_valid"):
        async with sessions.begin() as session:
            await session.execute(
                text(
                    "INSERT INTO staff_worker_audit"
                    " (worker_id, action, reason, changed_by, changed_at)"
                    " VALUES (:worker_id, :action, 'Motivo indebido', :actor, :now)"
                ),
                {
                    "worker_id": worker_id,
                    "action": action,
                    "actor": _EDITOR,
                    "now": _UPDATED_AT,
                },
            )


@pytest.mark.parametrize("action", ["ACTIVATED", "DEACTIVATED"])
async def test_hu15_el_check_admite_reason_en_cambios_de_estado(
    sessions: async_sessionmaker[AsyncSession], action: str
) -> None:
    worker_id = await _registered_worker(sessions)

    async with sessions.begin() as session:
        await session.execute(
            text(
                "INSERT INTO staff_worker_audit"
                " (worker_id, action, reason, changed_by, changed_at)"
                " VALUES (:worker_id, :action, 'Motivo permitido', :actor, :now)"
            ),
            {
                "worker_id": worker_id,
                "action": action,
                "actor": _EDITOR,
                "now": _DEACTIVATED_AT,
            },
        )

    async with sessions() as session:
        row = await session.scalar(
            select(StaffWorkerAuditRow).where(StaffWorkerAuditRow.action == action)
        )

    assert row is not None and row.reason == "Motivo permitido"
    assert row.worker_id == worker_id
    assert row.changed_by == _EDITOR
    assert row.changed_at == _DEACTIVATED_AT
