"""Repositorio de trabajadores contra PostgreSQL real (HU15). Necesita Docker.

Las tablas se crean con las migraciones de Alembic, igual que en producción. Cubre
guardar/leer/actualizar, búsqueda, filtros y paginación, bloqueo `FOR UPDATE`, el
lookup sin datos sensibles y la auditoría insertada (T-11).
"""

from collections.abc import AsyncIterator, Iterator
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.staff.application.ports.worker_repository import WorkerRef
from local_eventos.modules.staff.domain.audit import AuditAction, WorkerAudit
from local_eventos.modules.staff.domain.document import Document, WorkerDocumentType
from local_eventos.modules.staff.domain.enums import WorkerFunction, WorkerStatus
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.orm_models import StaffWorkerAuditRow
from local_eventos.modules.staff.infrastructure.worker_repository import (
    SqlAlchemyWorkerRepository,
)
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_ACTOR = UUID("11111111-1111-1111-1111-111111111111")
_NOW = datetime(2026, 11, 24, 15, 30, tzinfo=UTC)
_DEFAULT_RATE = Money(15000)


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
            text(
                "TRUNCATE staff_unavailabilities_audit, staff_unavailabilities, "
                "staff_attendance_audit, staff_attendance, "
                "staff_assignment_audit, staff_assignments, "
                "staff_worker_audit, staff_workers RESTART IDENTITY"
            )
        )
    yield engine
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _worker(
    name: str = "José Ramírez Quispe",
    number: str = "44125896",
    *,
    function: WorkerFunction | None = WorkerFunction.COOK,
    description: str | None = None,
    phone: str | None = "987654321",
    rate: Money | None = _DEFAULT_RATE,
    worker_id: UUID | None = None,
) -> Worker:
    return Worker.register(
        name=name,
        document_type=WorkerDocumentType.DNI,
        document_number=number,
        phone=phone,
        function=function,
        function_description=description,
        rate=rate,
        worker_id=worker_id,
    )


def _audit(
    worker: Worker,
    action: AuditAction = AuditAction.CREATED,
    reason: str | None = None,
) -> WorkerAudit:
    return WorkerAudit(
        worker_id=worker.id,
        action=action,
        changed_by=_ACTOR,
        changed_at=_NOW,
        reason=reason,
    )


async def test_ca15_1_guarda_y_lee(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker = _worker()
    async with sessions.begin() as session:
        await SqlAlchemyWorkerRepository(session).save(worker, _audit(worker))

    async with sessions() as session:
        saved = await SqlAlchemyWorkerRepository(session).get(worker.id)

    assert saved == worker


async def test_ca15_6_actualiza_sin_duplicar(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker = _worker()
    async with sessions.begin() as session:
        await SqlAlchemyWorkerRepository(session).save(worker, _audit(worker))

    worker.update(
        name="José Ramírez",
        document_type=WorkerDocumentType.DNI,
        document_number="44125896",
        phone="912345678",
        function=WorkerFunction.OTHER,
        function_description="Maestro de cocina",
    )
    async with sessions.begin() as session:
        await SqlAlchemyWorkerRepository(session).save(worker, _audit(worker, AuditAction.UPDATED))

    async with sessions() as session:
        saved = await SqlAlchemyWorkerRepository(session).get(worker.id)
        total = await session.scalar(select(func.count()).select_from(StaffWorkerAuditRow))

    assert saved == worker
    assert saved is not None and saved.function_description == "Maestro de cocina"
    assert total == 2


async def test_hu15_get_by_document_incluye_inactivos(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker = _worker(number="4412-5896")
    worker.deactivate()
    async with sessions.begin() as session:
        await SqlAlchemyWorkerRepository(session).save(
            worker, _audit(worker, AuditAction.DEACTIVATED, "Renuncia")
        )

    async with sessions() as session:
        repository = SqlAlchemyWorkerRepository(session)
        found = await repository.get_by_document(Document(WorkerDocumentType.DNI, "44125896"))
        missing = await repository.get_by_document(Document(WorkerDocumentType.DNI, "11111111"))

    assert found is not None and found.status is WorkerStatus.INACTIVE
    assert missing is None


async def test_ca15_8_busca_por_nombre_sin_tildes_y_por_documento(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        repository = SqlAlchemyWorkerRepository(session)
        first = _worker()
        second = _worker("Colegio San Martín", "20125478", function=WorkerFunction.WAITER)
        await repository.save(first, _audit(first))
        await repository.save(second, _audit(second))

    async with sessions() as session:
        repository = SqlAlchemyWorkerRepository(session)
        by_name = await repository.search(
            text="jose ramirez",
            function=None,
            status=None,
            page=1,
            page_size=50,
        )
        by_document = await repository.search(
            text="2012-5478",
            function=None,
            status=None,
            page=1,
            page_size=50,
        )
        wildcard = await repository.search(
            text="100%",
            function=None,
            status=None,
            page=1,
            page_size=50,
        )

    assert [w.name for w in by_name.items] == ["José Ramírez Quispe"]
    assert [w.name for w in by_document.items] == ["Colegio San Martín"]
    assert wildcard.items == []


async def test_hu15_filtros_y_paginacion_estable(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        repository = SqlAlchemyWorkerRepository(session)
        for worker in (
            _worker("Zoe Torres", "30125896", function=WorkerFunction.COOK),
            _worker("Ana Pérez", "30125897", function=WorkerFunction.WAITER),
            _worker("Luis Gómez", "30125898", function=WorkerFunction.COOK),
        ):
            await repository.save(worker, _audit(worker))
        inactive = _worker("Mario Ruiz", "30125899", function=WorkerFunction.COOK)
        inactive.deactivate()
        await repository.save(inactive, _audit(inactive, AuditAction.DEACTIVATED, "Baja temporal"))

    async with sessions() as session:
        repository = SqlAlchemyWorkerRepository(session)
        everyone = await repository.search(
            text="", function=None, status=None, page=1, page_size=50
        )
        cooks_active = await repository.search(
            text="", function=WorkerFunction.COOK, status=WorkerStatus.ACTIVE, page=1, page_size=50
        )
        cooks_all = await repository.search(
            text="", function=WorkerFunction.COOK, status=None, page=1, page_size=50
        )
        first_page = await repository.search(
            text="", function=None, status=None, page=1, page_size=2
        )
        second_page = await repository.search(
            text="", function=None, status=None, page=2, page_size=2
        )

    assert [w.name for w in everyone.items] == [
        "Ana Pérez",
        "Luis Gómez",
        "Mario Ruiz",
        "Zoe Torres",
    ]
    assert everyone.total == 4
    assert [w.name for w in cooks_active.items] == ["Luis Gómez", "Zoe Torres"]
    assert [w.name for w in cooks_all.items] == ["Luis Gómez", "Mario Ruiz", "Zoe Torres"]
    assert [w.name for w in first_page.items] == ["Ana Pérez", "Luis Gómez"]
    assert [w.name for w in second_page.items] == ["Mario Ruiz", "Zoe Torres"]
    assert first_page.total == second_page.total == 4


async def test_hu15_get_for_update_bloquea_y_lee(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker = _worker()
    async with sessions.begin() as session:
        await SqlAlchemyWorkerRepository(session).save(worker, _audit(worker))

    async with sessions.begin() as session:
        repository = SqlAlchemyWorkerRepository(session)
        locked = await repository.get_for_update(worker.id)

    assert locked == worker


async def test_ca15_12_lookup_no_expone_datos_sensibles(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker = _worker(function=WorkerFunction.OTHER, description="Maestro de cocina")
    async with sessions.begin() as session:
        await SqlAlchemyWorkerRepository(session).save(worker, _audit(worker))

    async with sessions() as session:
        reference = await SqlAlchemyWorkerRepository(session).lookup(worker.id)

    assert isinstance(reference, WorkerRef)
    assert reference == WorkerRef(
        id=worker.id,
        name="José Ramírez Quispe",
        function=WorkerFunction.OTHER,
        function_description="Maestro de cocina",
        status=WorkerStatus.ACTIVE,
    )
    assert {field.name for field in fields(WorkerRef)} == {
        "id",
        "name",
        "function",
        "function_description",
        "status",
    }


async def test_ca15_12_lookup_de_inactivo(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker = _worker()
    worker.deactivate()
    async with sessions.begin() as session:
        await SqlAlchemyWorkerRepository(session).save(
            worker, _audit(worker, AuditAction.DEACTIVATED, "Renuncia")
        )

    async with sessions() as session:
        reference = await SqlAlchemyWorkerRepository(session).lookup(worker.id)

    assert reference is not None and reference.status is WorkerStatus.INACTIVE


async def test_ca15_16_auditoria_insertada(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker = _worker()
    async with sessions.begin() as session:
        await SqlAlchemyWorkerRepository(session).save(worker, _audit(worker, AuditAction.CREATED))

    async with sessions.begin() as session:
        await SqlAlchemyWorkerRepository(session).save(
            worker, _audit(worker, AuditAction.DEACTIVATED, "Fin de temporada")
        )

    async with sessions() as session:
        audits = (
            await session.scalars(select(StaffWorkerAuditRow).order_by(StaffWorkerAuditRow.id))
        ).all()

    assert [row.action for row in audits] == ["CREATED", "DEACTIVATED"]
    assert audits[0].reason is None
    assert audits[1].reason == "Fin de temporada"
    assert all(row.worker_id == worker.id for row in audits)
    assert all(row.changed_by == _ACTOR for row in audits)
