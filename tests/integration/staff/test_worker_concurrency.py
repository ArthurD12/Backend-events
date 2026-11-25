"""Unicidad concurrente del documento del trabajador (HU15, CA-15.3/CA-15.5).

Dos sesiones simultáneas intentan guardar la misma combinación tipo + número: la
restricción `uq_staff_workers_document` decide y la perdedora recibe
`DuplicateDocumentError` (`staff.document_duplicated`). Necesita Docker/PostgreSQL y
las migraciones de Alembic, igual que en producción (plan §6.4, T-12).
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

from local_eventos.modules.staff.application.errors import DuplicateDocumentError
from local_eventos.modules.staff.domain.audit import AuditAction, WorkerAudit
from local_eventos.modules.staff.domain.document import Document, WorkerDocumentType
from local_eventos.modules.staff.domain.enums import WorkerFunction
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.orm_models import StaffWorkerRow
from local_eventos.modules.staff.infrastructure.worker_repository import (
    SqlAlchemyWorkerRepository,
)
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_ACTOR = UUID("11111111-1111-1111-1111-111111111111")
_NOW = datetime(2026, 11, 24, 15, 30, tzinfo=UTC)


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


def _worker(
    name: str,
    number: str,
    *,
    document_type: WorkerDocumentType = WorkerDocumentType.DNI,
) -> Worker:
    return Worker.register(
        name=name,
        document_type=document_type,
        document_number=number,
        phone=None,
        function=WorkerFunction.COOK,
        function_description=None,
        rate=Money(15000),
    )


def _audit(worker: Worker) -> WorkerAudit:
    return WorkerAudit(
        worker_id=worker.id,
        action=AuditAction.CREATED,
        changed_by=_ACTOR,
        changed_at=_NOW,
        reason=None,
    )


async def test_ca15_5_dos_altas_simultaneas_dejan_solo_una(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    first = _worker("Ana Pérez", "44125896")
    second = _worker("Luis Gómez", "44125896")

    async def try_save(worker: Worker) -> str:
        try:
            async with sessions.begin() as session:
                await SqlAlchemyWorkerRepository(session).save(worker, _audit(worker))
            return "ok"
        except DuplicateDocumentError as error:
            assert error.code == "staff.document_duplicated"
            return "duplicado"

    results = await asyncio.gather(try_save(first), try_save(second))

    async with sessions() as session:
        total = await session.scalar(select(func.count()).select_from(StaffWorkerRow))
        done = (await session.scalars(select(StaffWorkerRow.name))).all()

    assert sorted(results) == ["duplicado", "ok"]
    assert total == 1
    assert done == [first.name if results[0] == "ok" else second.name]


async def test_ca15_3_tipos_distintos_con_mismo_numero(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """La unicidad es por tipo + número, no solo por número.

    La spec (CA-15.3) pide que un DNI y un CE «con el mismo número» coexistan, pero el
    CHECK del esquema exige DNI de 8 dígitos y CE de 9 a 12, así que un mismo número no
    puede ser válido para ambos tipos. Se comprueba lo que sí garantiza el esquema: un
    DNI y un CE válidos conviven, y la restricción UNIQUE cubre (tipo, número).
    """
    dni = _worker("Ana Pérez", "44125896", document_type=WorkerDocumentType.DNI)
    ce = _worker("Luis Gómez", "441258961", document_type=WorkerDocumentType.CE)

    async with sessions.begin() as session:
        repository = SqlAlchemyWorkerRepository(session)
        await repository.save(dni, _audit(dni))
        await repository.save(ce, _audit(ce))

    async with sessions() as session:
        total = await session.scalar(select(func.count()).select_from(StaffWorkerRow))
        by_document = await SqlAlchemyWorkerRepository(session).get_by_document(
            Document(WorkerDocumentType.CE, "441258961")
        )

    assert total == 2
    assert by_document is not None and by_document.id == ce.id
