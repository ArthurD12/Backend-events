"""Restricción de exclusión de asignaciones contra PostgreSQL real (HU17, T-16).

Cubre los criterios de aceptación del no-solape a nivel de base de datos: solape en
el mismo evento y entre eventos (CA-17.7), intervalos contiguos aceptados
(CA-17.8), cruce de medianoche (CA-17.9), varias asignaciones no superpuestas al
mismo evento (CA-17.23) y liberación por anulación o evento cancelado
(CA-17.16/17.20). Además inserta dos filas solapadas por SQL directo para
comprobar que la garantía la impone PostgreSQL (SQLSTATE `23P01`,
`staff_assignments_no_overlap`) y no la aplicación.

Las tablas se crean con las migraciones de Alembic, igual que en producción.
Necesita Docker/PostgreSQL (plan §5.3, T-16).
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

from local_eventos.modules.staff.application.errors import AssignmentOverlapError
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import AssignmentAudit
from local_eventos.modules.staff.domain.document import WorkerDocumentType
from local_eventos.modules.staff.domain.enums import WorkerFunction
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.assignment_repository import (
    SqlAlchemyAssignmentRepository,
)
from local_eventos.modules.staff.infrastructure.mappers import worker_to_row
from local_eventos.modules.staff.infrastructure.orm_models import StaffAssignmentRow
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_ACTOR = UUID("11111111-1111-1111-1111-111111111111")
_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
_EVENT_ID = UUID("44444444-4444-4444-4444-444444444444")
_OTHER_EVENT_ID = UUID("55555555-5555-5555-5555-555555555555")
_NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
_START = datetime(2026, 12, 19, 18, 0, tzinfo=UTC)
_END = datetime(2026, 12, 19, 23, 0, tzinfo=UTC)

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


def _assignment(
    *,
    event_id: UUID = _EVENT_ID,
    start_at: datetime = _START,
    end_at: datetime = _END,
    assignment_id: UUID | None = None,
) -> Assignment:
    return Assignment.register(
        event_id=event_id,
        worker_id=_WORKER_ID,
        function=WorkerFunction.WAITER,
        start_at=start_at,
        end_at=end_at,
        pay=4500,
        assignment_id=assignment_id,
    )


def _created(assignment: Assignment) -> AssignmentAudit:
    return AssignmentAudit.created(
        assignment_id=assignment.id,
        actor_id=_ACTOR,
        occurred_at=_NOW,
    )


def _cancelled(assignment: Assignment) -> AssignmentAudit:
    return AssignmentAudit.cancelled(
        assignment_id=assignment.id,
        actor_id=_ACTOR,
        occurred_at=_NOW,
        reason="El cliente canceló el servicio",
    )


async def _count_assignments(sessions: async_sessionmaker[AsyncSession]) -> int:
    async with sessions() as session:
        total = await session.scalar(select(func.count()).select_from(StaffAssignmentRow))
    return int(total or 0)


async def _save_expecting_overlap(
    sessions: async_sessionmaker[AsyncSession],
    assignment: Assignment,
) -> None:
    with pytest.raises(AssignmentOverlapError):
        async with sessions.begin() as session:
            await SqlAlchemyAssignmentRepository(session).save(assignment, _created(assignment))


async def test_ca17_7_solape_mismo_evento_y_entre_eventos(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    existing = _assignment()

    async with sessions.begin() as session:
        await _add_worker(session)
        await SqlAlchemyAssignmentRepository(session).save(existing, _created(existing))

    # Mismo evento: 22:00–23:30 cruza 18:00–23:00.
    same_event = _assignment(
        start_at=datetime(2026, 12, 19, 22, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 23, 30, tzinfo=UTC),
        assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000001"),
    )
    # Otro evento con la misma ventana: también se cruza con el trabajador.
    other_event = _assignment(
        event_id=_OTHER_EVENT_ID,
        start_at=datetime(2026, 12, 19, 19, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 21, 0, tzinfo=UTC),
        assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000002"),
    )

    await _save_expecting_overlap(sessions, same_event)
    await _save_expecting_overlap(sessions, other_event)

    assert await _count_assignments(sessions) == 1


async def test_ca17_8_intervalos_contiguos_se_aceptan(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    morning = _assignment(
        start_at=datetime(2026, 12, 19, 8, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 12, 0, tzinfo=UTC),
        assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000003"),
    )
    afternoon = _assignment(
        start_at=datetime(2026, 12, 19, 12, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 16, 0, tzinfo=UTC),
        assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000004"),
    )

    async with sessions.begin() as session:
        await _add_worker(session)
        repository = SqlAlchemyAssignmentRepository(session)
        await repository.save(morning, _created(morning))
        await repository.save(afternoon, _created(afternoon))

    assert await _count_assignments(sessions) == 2


async def test_ca17_9_cruce_de_medianoche(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    overnight = _assignment(
        start_at=datetime(2026, 12, 19, 22, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 20, 2, 0, tzinfo=UTC),
        assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000005"),
    )

    async with sessions.begin() as session:
        await _add_worker(session)
        await SqlAlchemyAssignmentRepository(session).save(overnight, _created(overnight))

    # Madrugada siguiente: se superpone con la cola del cruce de medianoche.
    early_overlap = _assignment(
        start_at=datetime(2026, 12, 20, 0, 30, tzinfo=UTC),
        end_at=datetime(2026, 12, 20, 3, 0, tzinfo=UTC),
        assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000006"),
    )
    await _save_expecting_overlap(sessions, early_overlap)

    # Empieza exactamente a las 02:00, cuando la anterior termina: es contiguo.
    after = _assignment(
        start_at=datetime(2026, 12, 20, 2, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 20, 5, 0, tzinfo=UTC),
        assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000007"),
    )
    async with sessions.begin() as session:
        await SqlAlchemyAssignmentRepository(session).save(after, _created(after))

    assert await _count_assignments(sessions) == 2


async def test_ca17_23_varias_asignaciones_al_mismo_evento_sin_solape(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    slots = [
        _assignment(
            start_at=datetime(2026, 12, 20, 8, 0, tzinfo=UTC),
            end_at=datetime(2026, 12, 20, 10, 0, tzinfo=UTC),
            assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000010"),
        ),
        _assignment(
            start_at=datetime(2026, 12, 20, 10, 0, tzinfo=UTC),
            end_at=datetime(2026, 12, 20, 12, 0, tzinfo=UTC),
            assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000011"),
        ),
        _assignment(
            start_at=datetime(2026, 12, 20, 13, 0, tzinfo=UTC),
            end_at=datetime(2026, 12, 20, 15, 0, tzinfo=UTC),
            assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000012"),
        ),
    ]

    async with sessions.begin() as session:
        await _add_worker(session)
        repository = SqlAlchemyAssignmentRepository(session)
        for slot in slots:
            await repository.save(slot, _created(slot))

    assert await _count_assignments(sessions) == 3


async def test_ca17_16_anulacion_libera_el_hueco(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    cancelled = _assignment(assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000020"))
    cancelled.cancel()

    async with sessions.begin() as session:
        await _add_worker(session)
        await SqlAlchemyAssignmentRepository(session).save(cancelled, _cancelled(cancelled))

    replacement = _assignment(
        start_at=datetime(2026, 12, 19, 19, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 22, 0, tzinfo=UTC),
        assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000021"),
    )
    async with sessions.begin() as session:
        await SqlAlchemyAssignmentRepository(session).save(replacement, _created(replacement))

    assert await _count_assignments(sessions) == 2


async def test_ca17_20_liberacion_libera_el_hueco(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    released = _assignment(assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000030"))

    async with sessions.begin() as session:
        await _add_worker(session)
        await SqlAlchemyAssignmentRepository(session).save(released, _created(released))

    # Un evento cancelado deja la asignación con `occupies=false` (liberación perezosa).
    async with sessions.begin() as session:
        repository = SqlAlchemyAssignmentRepository(session)
        stored = await repository.get(released.id)
        assert stored is not None
        await repository.release([stored])

    replacement = _assignment(
        start_at=datetime(2026, 12, 19, 19, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 19, 22, 0, tzinfo=UTC),
        assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000031"),
    )
    async with sessions.begin() as session:
        await SqlAlchemyAssignmentRepository(session).save(replacement, _created(replacement))

    assert await _count_assignments(sessions) == 2


async def test_restriccion_sql_directo_rechaza_solape(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    first = _assignment(assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000040"))
    second = _assignment(
        start_at=datetime(2026, 12, 19, 22, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 20, 2, 0, tzinfo=UTC),
        assignment_id=UUID("aaaaaaaa-0000-0000-0000-000000000041"),
    )

    async with sessions.begin() as session:
        await _add_worker(session)
        await session.execute(_INSERT_ASSIGNMENT, _insert_params(first))

    with pytest.raises(IntegrityError) as excinfo:
        async with sessions.begin() as session:
            await session.execute(_INSERT_ASSIGNMENT, _insert_params(second))

    sqlstate = _sqlstate(excinfo.value)
    constraint = _constraint_name(excinfo.value)
    assert sqlstate == "23P01"
    assert constraint == "staff_assignments_no_overlap"
    assert await _count_assignments(sessions) == 1


def _insert_params(assignment: Assignment) -> dict[str, object]:
    return {
        "id": assignment.id,
        "event_id": assignment.event_id,
        "worker_id": assignment.worker_id,
        "start_at": assignment.start_at,
        "end_at": assignment.end_at,
    }


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
