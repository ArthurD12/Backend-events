"""Constraints de PostgreSQL y garantías transaccionales del personal (HU15).

Cubre lo que pidió la review contra PostgreSQL real con las migraciones de Alembic:
cada CHECK de `staff_workers` y `staff_worker_audit` mediante SQL directo, la edición
a un documento ajeno (CA-15.4), dos bajas simultáneas que auditan una sola vez y la
reversión de la ficha cuando falla su auditoría (plan §4/§6.2/§8.2). Necesita Docker.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.staff.application.errors import DuplicateDocumentError
from local_eventos.modules.staff.application.use_cases.change_worker_status import (
    DeactivateWorker,
)
from local_eventos.modules.staff.domain.audit import AuditAction, WorkerAudit
from local_eventos.modules.staff.domain.document import WorkerDocumentType
from local_eventos.modules.staff.domain.enums import WorkerFunction, WorkerStatus
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.orm_models import (
    StaffWorkerAuditRow,
    StaffWorkerRow,
)
from local_eventos.modules.staff.infrastructure.worker_repository import (
    SqlAlchemyWorkerRepository,
)
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_ACTOR = UUID("11111111-1111-1111-1111-111111111111")
_NOW = datetime(2026, 11, 24, 15, 30, tzinfo=UTC)

_INSERT_WORKER = (
    "INSERT INTO staff_workers"
    " (id, name, document_type, document_number, phone, worker_function,"
    " function_description, worker_type, rate_cents, overtime_applies,"
    " overtime_rate_cents, status)"
    " VALUES (:id, :name, :document_type, :document_number, :phone,"
    " :worker_function, :function_description, :worker_type, :rate_cents,"
    " :overtime_applies, :overtime_rate_cents, :status)"
)

_INSERT_AUDIT = (
    "INSERT INTO staff_worker_audit"
    " (worker_id, action, reason, changed_by, changed_at)"
    " VALUES (:worker_id, :action, :reason, :changed_by, :changed_at)"
)

_VALID_WORKER: dict[str, Any] = {
    "name": "Ana Pérez",
    "document_type": "DNI",
    "document_number": "44125896",
    "phone": "987654321",
    "worker_function": "COOK",
    "function_description": None,
    "worker_type": "FIXED",
    "rate_cents": 15000,
    "overtime_applies": False,
    "overtime_rate_cents": None,
    "status": "ACTIVE",
}


class _FixedClock:
    """Reloj determinista: todas las operaciones comparten el mismo instante."""

    def now(self) -> datetime:
        return _NOW


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


def _worker(name: str, number: str) -> Worker:
    return Worker.register(
        name=name,
        document_type=WorkerDocumentType.DNI,
        document_number=number,
        phone="987654321",
        function=WorkerFunction.COOK,
        rate=Money(15000),
    )


def _audit(worker: Worker, action: AuditAction = AuditAction.CREATED) -> WorkerAudit:
    return WorkerAudit(
        worker_id=worker.id,
        action=action,
        changed_by=_ACTOR,
        changed_at=_NOW,
        reason=None,
    )


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        pytest.param(
            {"document_number": "441258969"},
            "ck_staff_workers_document_valid",
            id="dni-de-nueve-digitos",
        ),
        pytest.param(
            {"document_type": "CE", "document_number": "44125896"},
            "ck_staff_workers_document_valid",
            id="ce-de-ocho-digitos",
        ),
        pytest.param(
            {"phone": "98765A321"},
            "ck_staff_workers_phone_digits",
            id="telefono-con-letra",
        ),
        pytest.param(
            {"worker_function": "OTHER"},
            "ck_staff_workers_function_description_valid",
            id="otro-sin-descripcion",
        ),
        pytest.param(
            {"function_description": "Cocina"},
            "ck_staff_workers_function_description_valid",
            id="descripcion-con-otra-funcion",
        ),
        pytest.param(
            {"overtime_applies": True},
            "ck_staff_workers_overtime_valid",
            id="hora-extra-sin-monto",
        ),
        pytest.param(
            {"overtime_rate_cents": 1000},
            "ck_staff_workers_overtime_valid",
            id="monto-sin-hora-extra",
        ),
        pytest.param(
            {"rate_cents": -1},
            "ck_staff_workers_rate_not_negative",
            id="tarifa-negativa",
        ),
        pytest.param(
            {"status": "RETIRED"},
            "ck_staff_workers_status_valid",
            id="estado-invalido",
        ),
    ],
)
async def test_hu15_los_checks_rechazan_datos_invalidos_con_sql_directo(
    engine: AsyncEngine,
    overrides: dict[str, Any],
    constraint: str,
) -> None:
    """Cada violación usa su propia transacción para no envenenar la conexión."""
    values = {**_VALID_WORKER, "id": uuid4(), **overrides}

    with pytest.raises(IntegrityError, match=constraint):
        async with engine.begin() as connection:
            await connection.execute(text(_INSERT_WORKER), values)

    async with engine.connect() as connection:
        total = await connection.scalar(text("SELECT count(*) FROM staff_workers"))

    assert total == 0


async def test_hu15_el_check_rechaza_accion_invalida_en_la_auditoria(
    engine: AsyncEngine,
) -> None:
    worker_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(text(_INSERT_WORKER), {**_VALID_WORKER, "id": worker_id})

    with pytest.raises(IntegrityError, match="ck_staff_worker_audit_action_valid"):
        async with engine.begin() as connection:
            await connection.execute(
                text(_INSERT_AUDIT),
                {
                    "worker_id": worker_id,
                    "action": "DELETED",
                    "reason": None,
                    "changed_by": _ACTOR,
                    "changed_at": _NOW,
                },
            )

    async with engine.connect() as connection:
        audits = await connection.scalar(text("SELECT count(*) FROM staff_worker_audit"))

    assert audits == 0


async def test_ca15_4_documento_ajeno_no_deja_cambios_parciales(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    first = _worker("Ana Pérez", "44125896")
    second = _worker("Luis Gómez", "44125897")

    async with sessions.begin() as session:
        repository = SqlAlchemyWorkerRepository(session)
        await repository.save(first, _audit(first))
        await repository.save(second, _audit(second))

    with pytest.raises(DuplicateDocumentError):
        async with sessions.begin() as session:
            repository = SqlAlchemyWorkerRepository(session)
            current = await repository.get(first.id)
            assert current is not None
            # Simula la carrera de edición: el dominio ya tiene el documento ajeno
            # cuando se hace flush; la UNIQUE decide y la transacción se revierte.
            current.update(
                name=current.name,
                document_type=WorkerDocumentType.DNI,
                document_number=second.document.number,
                phone=current.phone,
                function=current.function,
                function_description=current.function_description,
                rate=current.rate,
            )
            await repository.save(current, _audit(current, AuditAction.UPDATED))

    async with sessions() as session:
        repository = SqlAlchemyWorkerRepository(session)
        saved = await repository.get(first.id)
        audit_total = await session.scalar(select(func.count()).select_from(StaffWorkerAuditRow))

    assert saved is not None and saved.document.number == "44125896"
    assert audit_total == 2


async def test_hu15_dos_desactivaciones_simultaneas_auditan_una_sola_vez(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker = _worker("Ana Pérez", "44125896")
    async with sessions.begin() as session:
        await SqlAlchemyWorkerRepository(session).save(worker, _audit(worker))

    clock = _FixedClock()

    async def deactivate(reason: str) -> WorkerStatus:
        async with sessions.begin() as session:
            use_case = DeactivateWorker(SqlAlchemyWorkerRepository(session), clock)
            result = await use_case.execute(worker.id, reason, _ACTOR)
            return result.status

    results = await asyncio.gather(deactivate("Renuncia"), deactivate("Fin de temporada"))

    async with sessions() as session:
        saved = await SqlAlchemyWorkerRepository(session).get(worker.id)
        audits = (
            await session.scalars(
                select(StaffWorkerAuditRow).where(StaffWorkerAuditRow.action == "DEACTIVATED")
            )
        ).all()

    assert results == [WorkerStatus.INACTIVE, WorkerStatus.INACTIVE]
    assert saved is not None and saved.status is WorkerStatus.INACTIVE
    assert len(audits) == 1
    assert audits[0].worker_id == worker.id


async def test_hu15_un_fallo_de_auditoria_revierte_la_ficha(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker = _worker("Ana Pérez", "44125896")
    # La auditoría apunta a un trabajador inexistente: la FK debe rechazarla.
    broken_audit = WorkerAudit(
        worker_id=uuid4(),
        action=AuditAction.CREATED,
        changed_by=_ACTOR,
        changed_at=_NOW,
        reason=None,
    )

    with pytest.raises(IntegrityError, match="fk_staff_worker_audit_worker_id"):
        async with sessions.begin() as session:
            await SqlAlchemyWorkerRepository(session).save(worker, broken_audit)

    async with sessions() as session:
        saved = await session.get(StaffWorkerRow, worker.id)
        audit_total = await session.scalar(select(func.count()).select_from(StaffWorkerAuditRow))

    assert saved is None
    assert audit_total == 0
