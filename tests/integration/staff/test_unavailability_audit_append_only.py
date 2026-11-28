"""Auditoría y anulación de indisponibilidades en PostgreSQL real (HU16, T-13).

Contra PostgreSQL con las migraciones de Alembic (plan §5.2/§5.5). Comprueba que el
trigger de auditoría rechaza `UPDATE`/`DELETE` pero admite inserciones, que una
indisponibilidad se anula sin borrado físico (CA-16.18) y que la indisponibilidad y
su auditoría se escriben de forma atómica: si la auditoría falla, la transacción no
deja ni una ni otra. Necesita Docker.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.staff.domain.document import WorkerDocumentType
from local_eventos.modules.staff.domain.enums import (
    UnavailabilityKind,
    UnavailabilityStatus,
    WorkerFunction,
)
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.unavailability_audit import UnavailabilityAudit
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.mappers import worker_to_row
from local_eventos.modules.staff.infrastructure.orm_models import (
    StaffUnavailabilityAuditRow,
    StaffUnavailabilityRow,
    StaffWorkerRow,
)
from local_eventos.modules.staff.infrastructure.unavailability_repository import (
    SqlAlchemyUnavailabilityRepository,
)
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_ACTOR = UUID("11111111-1111-1111-1111-111111111111")
_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
_NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)
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


def _unavailability(*, unavailability_id: UUID | None = None) -> Unavailability:
    return Unavailability.register(
        worker_id=_WORKER_ID,
        kind=UnavailabilityKind.VACATION,
        start_at=_START,
        end_at=_END,
        unavailability_id=unavailability_id,
    )


def _created(unavailability: Unavailability) -> UnavailabilityAudit:
    return UnavailabilityAudit.created(
        unavailability_id=unavailability.id,
        actor_id=_ACTOR,
        occurred_at=_NOW,
    )


def _cancelled(unavailability: Unavailability) -> UnavailabilityAudit:
    return UnavailabilityAudit.cancelled(
        unavailability_id=unavailability.id,
        actor_id=_ACTOR,
        occurred_at=_NOW,
        reason="La trabajadora pidió vacaciones en otra fecha",
    )


async def _save(
    unavailability: Unavailability,
    sessions: async_sessionmaker[AsyncSession],
    audit: UnavailabilityAudit | None = None,
) -> None:
    saved_audit = _created(unavailability) if audit is None else audit
    async with sessions.begin() as session:
        await _add_worker(session)
        await SqlAlchemyUnavailabilityRepository(session).save(unavailability, saved_audit)


async def _count(sessions: async_sessionmaker[AsyncSession], model: type[Any]) -> int:
    async with sessions() as session:
        total = await session.scalar(select(func.count()).select_from(model))
    return int(total or 0)


async def test_la_auditoria_rechaza_update_y_delete_pero_admite_insert(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    unavailability = _unavailability()
    await _save(unavailability, sessions)

    # Una inserción válida (acción CANCELLED con motivo) sí se admite.
    async with sessions.begin() as session:
        await session.execute(
            text(
                "INSERT INTO staff_unavailabilities_audit"
                " (unavailability_id, action, reason, actor_id, occurred_at)"
                " VALUES (:unavailability_id, 'CANCELLED', 'Vacaciones cambiadas', :actor, :now)"
            ),
            {
                "unavailability_id": unavailability.id,
                "actor": _ACTOR,
                "now": _NOW,
            },
        )

    assert await _count(sessions, StaffUnavailabilityAuditRow) == 2

    statements = [
        "UPDATE staff_unavailabilities_audit SET reason = reason",
        "DELETE FROM staff_unavailabilities_audit",
    ]
    for statement in statements:
        with pytest.raises(DBAPIError, match="no se modifica ni se borra"):
            async with sessions.begin() as session:
                await session.execute(text(statement))

    assert await _count(sessions, StaffUnavailabilityAuditRow) == 2


async def test_ca16_18_anulacion_sin_borrado_fisico(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    unavailability = _unavailability()
    await _save(unavailability, sessions)

    unavailability.cancel()
    async with sessions.begin() as session:
        await SqlAlchemyUnavailabilityRepository(session).save(
            unavailability, _cancelled(unavailability)
        )

    async with sessions() as session:
        row = await session.scalar(
            select(StaffUnavailabilityRow).where(StaffUnavailabilityRow.id == unavailability.id)
        )
        audits = (
            await session.scalars(
                select(StaffUnavailabilityAuditRow)
                .where(StaffUnavailabilityAuditRow.unavailability_id == unavailability.id)
                .order_by(StaffUnavailabilityAuditRow.id)
            )
        ).all()

    assert row is not None
    assert row.status == UnavailabilityStatus.CANCELLED.value
    assert [audit.action for audit in audits] == ["CREATED", "CANCELLED"]
    assert await _count(sessions, StaffUnavailabilityRow) == 1

    with pytest.raises(DBAPIError, match="no se borra físicamente"):
        async with sessions.begin() as session:
            await session.execute(
                text("DELETE FROM staff_unavailabilities WHERE id = :id"),
                {"id": unavailability.id},
            )

    assert await _count(sessions, StaffUnavailabilityRow) == 1


async def test_rollback_si_falla_la_auditoria_no_deja_indisponibilidad(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """La atomicidad es de la transacción, no un comportamiento de producción.

    La indisponibilidad y su auditoría se escriben en la misma transacción (plan §5.5).
    Si una auditoría viola un CHECK, el rollback debe deshacer también la
    indisponibilidad: no se modifica código de producción, se usa una auditoría inválida.
    """

    unavailability = _unavailability()

    with pytest.raises(IntegrityError, match="ck_staff_unavailabilities_audit_reason_valid"):
        async with sessions.begin() as session:
            await _add_worker(session)
            await SqlAlchemyUnavailabilityRepository(session).save(
                unavailability, _created(unavailability)
            )
            # `CREATED` con motivo viola ck_staff_unavailabilities_audit_reason_valid.
            await session.execute(
                text(
                    "INSERT INTO staff_unavailabilities_audit"
                    " (unavailability_id, action, reason, actor_id, occurred_at)"
                    " VALUES (:unavailability_id, 'CREATED', 'Motivo indebido', :actor, :now)"
                ),
                {
                    "unavailability_id": unavailability.id,
                    "actor": _ACTOR,
                    "now": _NOW,
                },
            )

    assert await _count(sessions, StaffUnavailabilityRow) == 0
    assert await _count(sessions, StaffUnavailabilityAuditRow) == 0
    # El trabajador se insertó en la misma transacción y también se revierte.
    assert await _count(sessions, StaffWorkerRow) == 0
