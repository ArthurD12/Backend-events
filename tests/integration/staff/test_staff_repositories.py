"""Personal contra PostgreSQL real (HU15–HU17). Necesita Docker.

Prueba lo que solo la base puede garantizar: el documento único y la restricción de exclusión
de RN12, aunque se salte la aplicación.
"""

from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.staff.application.errors import (
    AssignmentOverlapError,
    DocumentTakenError,
)
from local_eventos.modules.staff.application.ports.worker_repository import WorkerFilters
from local_eventos.modules.staff.domain.assignment import Assignment, AssignmentStatus
from local_eventos.modules.staff.domain.period import Period
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.worker import (
    DocumentType,
    Worker,
    WorkerData,
    WorkerFunction,
    WorkerType,
)
from local_eventos.modules.staff.infrastructure.assignment_repository import (
    SqlAlchemyAssignmentRepository,
)
from local_eventos.modules.staff.infrastructure.unavailability_repository import (
    SqlAlchemyUnavailabilityRepository,
)
from local_eventos.modules.staff.infrastructure.worker_repository import (
    SqlAlchemyWorkerRepository,
)
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 11, 25, 15, tzinfo=UTC)
DAY = date(2026, 12, 19)
USER = uuid4()


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
    yield engine
    async with engine.begin() as connection:
        await connection.execute(
            text("TRUNCATE staff_assignments, staff_unavailability, staff_workers")
        )
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _worker(number: str = "40000001", **changes: object) -> Worker:
    data = WorkerData(
        name="José Ramírez", document_type=DocumentType.DNI, document_number=number,
        phone="987654321", function=WorkerFunction.WAITER, worker_type=WorkerType.EVENTUAL,
        reference_rate_cents=12_000,
    )  # fmt: skip
    return Worker.register(replace(data, **changes), created_by=USER, now=NOW)  # type: ignore[arg-type]


def _assignment(worker: Worker, period: Period, event_id: UUID | None = None) -> Assignment:
    return Assignment.create(
        worker_id=worker.id, event_id=event_id or uuid4(), event_code="EVT-2026-0001",
        function=WorkerFunction.WAITER, period=period, agreed_pay_cents=12_000,
        created_by=USER, now=NOW,
    )  # fmt: skip


async def _save(sessions: async_sessionmaker[AsyncSession], *workers: Worker) -> None:
    async with sessions.begin() as session:
        for worker in workers:
            await SqlAlchemyWorkerRepository(session).add(worker)


async def test_ca15_guarda_lee_y_filtra_trabajadores(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    jose = _worker()
    ana = _worker("40000002", name="Ana Torres", function=WorkerFunction.COOK)
    ce = _worker("AB1234567", document_type=DocumentType.CE, worker_type=WorkerType.FIXED,
                 name="Zoe Díaz")  # fmt: skip
    await _save(sessions, jose, ana, ce)
    ana.set_active(False, updated_by=USER, now=NOW)
    async with sessions.begin() as session:
        await SqlAlchemyWorkerRepository(session).update(ana)

    async with sessions() as session:
        repository = SqlAlchemyWorkerRepository(session)
        saved = await repository.get(jose.id)
        by_document = await repository.get_by_document(ce.document)
        everyone = await repository.search(WorkerFilters())
        by_text = await repository.search(WorkerFilters(text="jose ramirez"))
        by_number = await repository.search(WorkerFilters(text="ab123"))
        cooks = await repository.search(WorkerFilters(function=WorkerFunction.COOK))
        fixed = await repository.search(WorkerFilters(worker_type=WorkerType.FIXED))
        active = await repository.search(WorkerFilters(active=True))
        many = await repository.get_many([jose.id, ce.id])

    assert saved == jose
    assert by_document == ce
    assert [w.name for w in everyone] == ["Ana Torres", "José Ramírez", "Zoe Díaz"]
    assert [w.id for w in by_text] == [jose.id]
    assert [w.id for w in by_number] == [ce.id]
    assert [w.id for w in cooks] == [ana.id]
    assert [w.id for w in fixed] == [ce.id]
    assert {w.id for w in active} == {jose.id, ce.id}
    assert {w.id for w in many} == {jose.id, ce.id}


async def test_ca15_2_la_base_impide_documento_repetido(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _save(sessions, _worker())

    with pytest.raises(DocumentTakenError):
        await _save(sessions, _worker(name="Otra persona"))
    other = _worker("40000002")
    await _save(sessions, other)
    other.update(
        WorkerData(
            name=other.name, document_type=DocumentType.DNI, document_number="40000001",
            phone=other.phone, function=other.function, worker_type=other.worker_type,
            reference_rate_cents=0,
        ),
        updated_by=USER, now=NOW,
    )  # fmt: skip
    with pytest.raises(DocumentTakenError):
        async with sessions.begin() as session:
            await SqlAlchemyWorkerRepository(session).update(other)


async def test_ca16_indisponibilidad_guarda_cruza_y_se_quita(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker = _worker()
    await _save(sessions, worker)
    night = Unavailability.create(
        worker_id=worker.id, period=Period.on(DAY, time(20), time(3)), reason="Viaje",
        created_by=USER, now=NOW,
    )  # fmt: skip
    morning = Unavailability.create(
        worker_id=worker.id, period=Period.on(DAY, time(8), time(12)), reason=None,
        created_by=USER, now=NOW,
    )  # fmt: skip
    async with sessions.begin() as session:
        repository = SqlAlchemyUnavailabilityRepository(session)
        await repository.add(night)
        await repository.add(morning)

    async with sessions.begin() as session:
        repository = SqlAlchemyUnavailabilityRepository(session)
        listed = await repository.list_for_worker(worker.id)
        crossing = await repository.list_overlapping(Period.on(DAY, time(11), time(21)))
        border = await repository.list_overlapping(Period.on(DAY, time(12), time(20)))
        other = await repository.list_overlapping(Period.on(DAY, time(0), time(23)),
                                                  worker_id=uuid4())  # fmt: skip
        await repository.remove(morning.id)

    async with sessions() as session:
        remaining = await SqlAlchemyUnavailabilityRepository(session).list_for_worker(worker.id)

    assert listed == [morning, night]
    assert crossing == [morning, night]
    assert border == []  # [inicio, fin): de 12:00 a 20:00 solo toca los bordes
    assert other == []
    assert remaining == [night]


async def test_ca17_guarda_lee_y_retira_asignaciones(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker = _worker()
    await _save(sessions, worker)
    event_id = uuid4()
    late = _assignment(worker, Period.on(DAY, time(18), time(2)), event_id)
    early = _assignment(worker, Period.on(DAY, time(9), time(13)), event_id)
    async with sessions.begin() as session:
        repository = SqlAlchemyAssignmentRepository(session)
        await repository.add(late)
        await repository.add(early)
    early.withdraw(reason="Ya no", withdrawn_by=USER, now=NOW)
    async with sessions.begin() as session:
        await SqlAlchemyAssignmentRepository(session).update(early)

    async with sessions() as session:
        repository = SqlAlchemyAssignmentRepository(session)
        listed = await repository.list_for_event(event_id)
        active = await repository.list_active_overlapping(Period.on(DAY, time(0), time(23)))
        saved = await repository.get(early.id)

    assert listed == [early, late]
    assert saved is not None and saved.status is AssignmentStatus.WITHDRAWN
    assert saved.withdrawal == early.withdrawal
    assert active == [late]


async def test_rn12_la_restriccion_rechaza_el_cruce_aunque_se_salte_la_aplicacion(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker = _worker()
    await _save(sessions, worker)
    first = _assignment(worker, Period.on(DAY, time(20), time(3)))
    async with sessions.begin() as session:
        await SqlAlchemyAssignmentRepository(session).add(first)

    with pytest.raises(AssignmentOverlapError) as error:
        async with sessions.begin() as session:
            await SqlAlchemyAssignmentRepository(session).add(
                _assignment(worker, Period.on(DAY, time(23), time(4)))
            )
    with pytest.raises(IntegrityError) as direct:
        async with sessions.begin() as session:
            await session.execute(
                text(
                    "INSERT INTO staff_assignments (id, worker_id, event_id, event_code, function,"
                    " period, agreed_pay_cents, status, created_by, created_at) VALUES"
                    " (:id, :worker, :event, 'EVT-2026-0009', 'WAITER',"
                    " tstzrange('2026-12-20 02:00+00', '2026-12-20 04:00+00', '[)'), 0,"
                    " 'ACTIVE', :user, now())"
                ),
                {"id": uuid4(), "worker": worker.id, "event": uuid4(), "user": USER},
            )

    assert error.value.code == "staff.assignment_overlap"
    assert error.value.event_code is None
    assert "ex_staff_assignments_no_overlap" in str(direct.value.orig)


async def test_rn12_bordes_que_se_tocan_otro_trabajador_y_retirar_liberan_el_horario(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker, other = _worker(), _worker("40000002")
    await _save(sessions, worker, other)
    morning = _assignment(worker, Period.on(DAY, time(8), time(18)))
    async with sessions.begin() as session:
        repository = SqlAlchemyAssignmentRepository(session)
        await repository.add(morning)
        await repository.add(_assignment(worker, Period.on(DAY, time(18), time(23))))
        await repository.add(_assignment(other, Period.on(DAY, time(8), time(18))))
    morning.withdraw(reason=None, withdrawn_by=USER, now=NOW)
    async with sessions.begin() as session:
        await SqlAlchemyAssignmentRepository(session).update(morning)

    async with sessions.begin() as session:
        await SqlAlchemyAssignmentRepository(session).add(
            _assignment(worker, Period.on(DAY, time(9), time(12)))
        )

    async with sessions() as session:
        active = await SqlAlchemyAssignmentRepository(session).list_active_overlapping(
            Period.on(DAY, time(0), time(23)), worker_id=worker.id
        )
    assert [a.period.local_start for a in active] == [time(9), time(18)]


async def test_retiro_y_estado_son_coherentes_en_la_base(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    worker = _worker()
    await _save(sessions, worker)

    with pytest.raises(IntegrityError) as error:
        async with sessions.begin() as session:
            await session.execute(
                text(
                    "INSERT INTO staff_assignments (id, worker_id, event_id, event_code, function,"
                    " period, agreed_pay_cents, status, created_by, created_at) VALUES"
                    " (:id, :worker, :event, 'EVT-2026-0009', 'WAITER',"
                    " tstzrange('2026-12-20 02:00+00', '2026-12-20 04:00+00', '[)'), 0,"
                    " 'WITHDRAWN', :user, now())"
                ),
                {"id": uuid4(), "worker": worker.id, "event": uuid4(), "user": USER},
            )
    assert "withdrawal_matches_status" in str(error.value.orig)
