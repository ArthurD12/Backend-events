"""Repositorio de indisponibilidades contra PostgreSQL real (HU16, T-12). Necesita Docker.

Las tablas se crean con las migraciones de Alembic, igual que en producción. Cubre el
round-trip con auditoría en la misma transacción, la reversión cuando falla la
auditoría, los listados por trabajador y ventana, el solape semiabierto (CA-16.13), los
intervalos contiguos y el cruce de medianoche (CA-16.14), y que
`list_active_overlapping` solo devuelva `ACTIVE`.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
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
)
from local_eventos.modules.staff.infrastructure.unavailability_repository import (
    SqlAlchemyUnavailabilityRepository,
)
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_ACTOR = UUID("11111111-1111-1111-1111-111111111111")
_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
_OTHER_WORKER_ID = UUID("33333333-3333-3333-3333-333333333333")
_NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


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
                "staff_attendance_audit, staff_attendance, "
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
    name: str = "Ana Pérez",
    number: str = "44125896",
    worker_id: UUID = _WORKER_ID,
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
    session.add(worker_to_row(worker))
    await session.flush()


def _unavailability(
    *,
    worker_id: UUID = _WORKER_ID,
    kind: UnavailabilityKind = UnavailabilityKind.VACATION,
    description: str | None = None,
    start_at: datetime,
    end_at: datetime,
    unavailability_id: UUID | None = None,
) -> Unavailability:
    return Unavailability.register(
        worker_id=worker_id,
        kind=kind,
        description=description,
        start_at=start_at,
        end_at=end_at,
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


async def _count(sessions: async_sessionmaker[AsyncSession], model: type[Any]) -> int:
    async with sessions() as session:
        total = await session.scalar(select(func.count()).select_from(model))
    return int(total or 0)


async def test_round_trip_y_auditoria_en_la_misma_transaccion(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    # Hora de Lima (UTC-5) a las 13:00 → 18:00 UTC.
    lima = timezone(timedelta(hours=-5))
    unavailability = _unavailability(
        start_at=datetime(2026, 12, 19, 13, 0, tzinfo=lima),
        end_at=datetime(2026, 12, 19, 18, 0, tzinfo=lima),
    )

    async with sessions.begin() as session:
        await _add_worker(session)
        repository = SqlAlchemyUnavailabilityRepository(session)
        await repository.save(unavailability, _created(unavailability))
        # Ambas filas están visibles en la misma transacción, sin commit intermedio.
        inside = await session.scalar(select(func.count()).select_from(StaffUnavailabilityAuditRow))
        pending = await repository.get(unavailability.id)
        assert inside == 1
        assert pending is not None

    async with sessions() as session:
        repository = SqlAlchemyUnavailabilityRepository(session)
        saved = await repository.get(unavailability.id)
        audits = (
            await session.scalars(
                select(StaffUnavailabilityAuditRow).where(
                    StaffUnavailabilityAuditRow.unavailability_id == unavailability.id
                )
            )
        ).all()

    assert saved is not None
    assert saved.id == unavailability.id
    assert saved.worker_id == _WORKER_ID
    assert saved.kind is UnavailabilityKind.VACATION
    assert saved.description is None
    assert saved.start_at == datetime(2026, 12, 19, 18, 0, tzinfo=UTC)
    assert saved.start_at.tzinfo is UTC
    assert saved.end_at == datetime(2026, 12, 19, 23, 0, tzinfo=UTC)
    assert saved.status is UnavailabilityStatus.ACTIVE

    assert len(audits) == 1
    assert audits[0].action == "CREATED"
    assert audits[0].reason is None
    assert audits[0].previous_values is None
    assert audits[0].new_values is None


async def test_get_for_update_lee_la_fila(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    unavailability = _unavailability(
        start_at=datetime(2026, 12, 19, 18, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 23, 0, tzinfo=UTC),
    )

    async with sessions.begin() as session:
        await _add_worker(session)
        await SqlAlchemyUnavailabilityRepository(session).save(
            unavailability, _created(unavailability)
        )

    async with sessions.begin() as session:
        locked = await SqlAlchemyUnavailabilityRepository(session).get_for_update(unavailability.id)

    assert locked is not None and locked.id == unavailability.id


async def test_una_auditoria_fallida_revierte_la_indisponibilidad(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    unavailability = _unavailability(
        start_at=datetime(2026, 12, 19, 18, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 23, 0, tzinfo=UTC),
    )
    # La auditoría apunta a una indisponibilidad inexistente: la FK debe rechazarla.
    broken = UnavailabilityAudit.created(
        unavailability_id=UUID("99999999-9999-9999-9999-999999999999"),
        actor_id=_ACTOR,
        occurred_at=_NOW,
    )

    with pytest.raises(IntegrityError, match="fk_staff_unavailabilities_audit_unavailability_id"):
        async with sessions.begin() as session:
            await _add_worker(session)
            await SqlAlchemyUnavailabilityRepository(session).save(unavailability, broken)

    async with sessions() as session:
        saved = await session.get(StaffUnavailabilityRow, unavailability.id)

    assert saved is None
    assert await _count(sessions, StaffUnavailabilityRow) == 0
    assert await _count(sessions, StaffUnavailabilityAuditRow) == 0


async def test_list_by_worker_incluye_canceladas_y_filtra_por_ventana(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    morning = _unavailability(
        start_at=datetime(2026, 12, 19, 8, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 12, 0, tzinfo=UTC),
        unavailability_id=UUID("aaaaaaaa-0000-0000-0000-000000000001"),
    )
    afternoon = _unavailability(
        start_at=datetime(2026, 12, 19, 14, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 16, 0, tzinfo=UTC),
        unavailability_id=UUID("aaaaaaaa-0000-0000-0000-000000000002"),
    )
    cancelled = _unavailability(
        start_at=datetime(2026, 12, 19, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 14, 0, tzinfo=UTC),
        unavailability_id=UUID("aaaaaaaa-0000-0000-0000-000000000003"),
    )
    cancelled.cancel()
    other_worker = _unavailability(
        worker_id=_OTHER_WORKER_ID,
        start_at=datetime(2026, 12, 19, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 11, 0, tzinfo=UTC),
        unavailability_id=UUID("aaaaaaaa-0000-0000-0000-000000000004"),
    )

    async with sessions.begin() as session:
        await _add_worker(session)
        await _add_worker(session, name="Luis Gómez", number="44125897", worker_id=_OTHER_WORKER_ID)
        repository = SqlAlchemyUnavailabilityRepository(session)
        await repository.save(morning, _created(morning))
        await repository.save(afternoon, _created(afternoon))
        await repository.save(cancelled, _cancelled(cancelled))
        await repository.save(other_worker, _created(other_worker))

    async with sessions() as session:
        repository = SqlAlchemyUnavailabilityRepository(session)
        everything = await repository.list_by_worker(_WORKER_ID)
        window = await repository.list_by_worker(
            _WORKER_ID,
            datetime(2026, 12, 19, 9, 0, tzinfo=UTC),
            datetime(2026, 12, 19, 13, 0, tzinfo=UTC),
        )
        all_workers = await repository.list(
            start_at=datetime(2026, 12, 19, 9, 0, tzinfo=UTC),
            end_at=datetime(2026, 12, 19, 11, 0, tzinfo=UTC),
        )

    assert [item.id for item in everything] == [morning.id, cancelled.id, afternoon.id]
    assert everything[1].status is UnavailabilityStatus.CANCELLED
    # La ventana [09,13) corta antes de la tarde: excluye `afternoon`.
    assert [item.id for item in window] == [morning.id, cancelled.id]
    assert {item.id for item in all_workers} == {morning.id, cancelled.id, other_worker.id}


async def test_list_active_overlapping_es_semiabierto_y_solo_activas(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    active = _unavailability(
        start_at=datetime(2026, 12, 19, 18, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 23, 0, tzinfo=UTC),
        unavailability_id=UUID("bbbbbbbb-0000-0000-0000-000000000001"),
    )
    cancelled = _unavailability(
        start_at=datetime(2026, 12, 19, 19, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 22, 0, tzinfo=UTC),
        unavailability_id=UUID("bbbbbbbb-0000-0000-0000-000000000002"),
    )
    cancelled.cancel()
    other_worker = _unavailability(
        worker_id=_OTHER_WORKER_ID,
        start_at=datetime(2026, 12, 19, 18, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 23, 0, tzinfo=UTC),
        unavailability_id=UUID("bbbbbbbb-0000-0000-0000-000000000003"),
    )

    async with sessions.begin() as session:
        await _add_worker(session)
        await _add_worker(session, name="Luis Gómez", number="44125897", worker_id=_OTHER_WORKER_ID)
        repository = SqlAlchemyUnavailabilityRepository(session)
        await repository.save(active, _created(active))
        await repository.save(cancelled, _cancelled(cancelled))
        await repository.save(other_worker, _created(other_worker))

    async with sessions() as session:
        repository = SqlAlchemyUnavailabilityRepository(session)
        both = await repository.list_active_overlapping(
            datetime(2026, 12, 19, 17, 0, tzinfo=UTC),
            datetime(2026, 12, 20, 0, 0, tzinfo=UTC),
            [_WORKER_ID, _OTHER_WORKER_ID],
        )
        only_worker = await repository.list_active_overlapping(
            datetime(2026, 12, 19, 17, 0, tzinfo=UTC),
            datetime(2026, 12, 20, 0, 0, tzinfo=UTC),
            [_WORKER_ID],
        )
        # Empieza justo cuando la activa termina: contiguo, no solapa.
        contiguous = await repository.list_active_overlapping(
            datetime(2026, 12, 19, 23, 0, tzinfo=UTC),
            datetime(2026, 12, 20, 2, 0, tzinfo=UTC),
            [_WORKER_ID, _OTHER_WORKER_ID],
        )
        # Termina justo cuando empieza: tampoco solapa (semiabierto).
        before = await repository.list_active_overlapping(
            datetime(2026, 12, 19, 15, 0, tzinfo=UTC),
            datetime(2026, 12, 19, 18, 0, tzinfo=UTC),
            [_WORKER_ID, _OTHER_WORKER_ID],
        )
        no_workers = await repository.list_active_overlapping(
            datetime(2026, 12, 19, 17, 0, tzinfo=UTC),
            datetime(2026, 12, 20, 0, 0, tzinfo=UTC),
            [],
        )

    assert {item.id for item in both} == {active.id, other_worker.id}
    assert all(item.status is UnavailabilityStatus.ACTIVE for item in both)
    assert [item.id for item in only_worker] == [active.id]
    assert contiguous == []
    assert before == []
    assert no_workers == []


async def test_contiguos_no_solapan_y_cruce_de_medianoche(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    morning = _unavailability(
        start_at=datetime(2026, 12, 19, 8, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 12, 0, tzinfo=UTC),
        unavailability_id=UUID("cccccccc-0000-0000-0000-000000000001"),
    )
    afternoon = _unavailability(
        start_at=datetime(2026, 12, 19, 12, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 16, 0, tzinfo=UTC),
        unavailability_id=UUID("cccccccc-0000-0000-0000-000000000002"),
    )
    overnight = _unavailability(
        start_at=datetime(2026, 12, 19, 22, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 20, 2, 0, tzinfo=UTC),
        unavailability_id=UUID("cccccccc-0000-0000-0000-000000000003"),
    )

    async with sessions.begin() as session:
        await _add_worker(session)
        repository = SqlAlchemyUnavailabilityRepository(session)
        await repository.save(morning, _created(morning))
        await repository.save(afternoon, _created(afternoon))
        await repository.save(overnight, _created(overnight))

    async with sessions() as session:
        repository = SqlAlchemyUnavailabilityRepository(session)
        first_slot = await repository.list_active_overlapping(
            datetime(2026, 12, 19, 8, 0, tzinfo=UTC),
            datetime(2026, 12, 19, 12, 0, tzinfo=UTC),
            [_WORKER_ID],
        )
        second_slot = await repository.list_active_overlapping(
            datetime(2026, 12, 19, 12, 0, tzinfo=UTC),
            datetime(2026, 12, 19, 16, 0, tzinfo=UTC),
            [_WORKER_ID],
        )
        # La medianoche siguiente cae dentro del cruce [22:00, 02:00).
        early_morning = await repository.list_active_overlapping(
            datetime(2026, 12, 20, 0, 30, tzinfo=UTC),
            datetime(2026, 12, 20, 3, 0, tzinfo=UTC),
            [_WORKER_ID],
        )
        # Empieza justo al terminar el cruce: contiguo.
        after_overnight = await repository.list_active_overlapping(
            datetime(2026, 12, 20, 2, 0, tzinfo=UTC),
            datetime(2026, 12, 20, 5, 0, tzinfo=UTC),
            [_WORKER_ID],
        )

    assert [item.id for item in first_slot] == [morning.id]
    assert [item.id for item in second_slot] == [afternoon.id]
    assert [item.id for item in early_morning] == [overnight.id]
    assert after_overnight == []
