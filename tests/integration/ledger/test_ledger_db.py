"""Pagos, movimientos y anulaciones contra PostgreSQL real (HU19–HU22). Necesita Docker.

Las tablas y los triggers de solo inserción se crean con las migraciones, igual que en producción.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.ledger.application.errors import PaymentAlreadyVoidedError
from local_eventos.modules.ledger.application.ports.movement_repository import (
    MovementFilters,
    MovementState,
)
from local_eventos.modules.ledger.application.use_cases.cash import CashTotals, EventCash
from local_eventos.modules.ledger.application.use_cases.movements import (
    ListMovements,
    MovementRequest,
    RecordMovement,
    VoidMovement,
)
from local_eventos.modules.ledger.application.use_cases.payments import (
    PaymentRequest,
    RecordPayment,
    VoidPayment,
)
from local_eventos.modules.ledger.domain.movement import MovementCategory, MovementType
from local_eventos.modules.ledger.domain.payment import PaymentKind, PaymentMethod, PaymentVoid
from local_eventos.modules.ledger.infrastructure.movement_repository import (
    SqlAlchemyMovementRepository,
)
from local_eventos.modules.ledger.infrastructure.payment_repository import (
    SqlAlchemyPaymentRepository,
)
from local_eventos.shared.infrastructure.db import create_engine
from tests.unit.ledger.fakes import FakeLedgerClock

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
TODAY = date(2026, 11, 22)
NOW = datetime(2026, 11, 22, 15, tzinfo=UTC)
_TABLES = (
    "ledger_payment_voids, ledger_payments, ledger_payment_counters,"
    " ledger_movement_voids, ledger_movements"
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
    yield engine
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {_TABLES}"))
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _request(kind: PaymentKind = PaymentKind.INSTALLMENT, **changes: object) -> PaymentRequest:
    data: dict[str, object] = {
        "contract_id": uuid4(),
        "kind": kind,
        "amount_cents": 10_000,
        "method": PaymentMethod.TRANSFER,
        "reference": "Op 1",
        "paid_on": TODAY,
        "recorded_by": uuid4(),
        **changes,
    }
    return PaymentRequest(**data)  # type: ignore[arg-type]


def _movement(**changes: object) -> MovementRequest:
    data: dict[str, object] = {
        "type": MovementType.EXPENSE,
        "category": MovementCategory.SUPPLIES,
        "concept": "Insumos",
        "amount_cents": 30_000,
        "method": PaymentMethod.CASH,
        "reference": None,
        "occurred_on": TODAY,
        "event_id": None,
        "recorded_by": uuid4(),
        **changes,
    }
    return MovementRequest(**data)  # type: ignore[arg-type]


async def test_ca20_1_numeros_correlativos_y_anulacion_en_la_base(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        repo = SqlAlchemyPaymentRepository(session)
        first = await RecordPayment(repo)(_request(), now=NOW, today=TODAY)
        second = await RecordPayment(repo)(
            _request(contract_id=first.contract_id), now=NOW, today=TODAY
        )
        await VoidPayment(repo)(second.id, reason="Error", voided_by=uuid4(), now=NOW)

    async with sessions() as session:
        repo = SqlAlchemyPaymentRepository(session)
        entries = await repo.entries_for_contract(first.contract_id)

    assert [(e.payment.number, e.is_voided) for e in entries] == [
        ("PAG-2026-0001", False),
        ("PAG-2026-0002", True),
    ]
    assert entries[0].payment == first


async def test_dos_anulaciones_del_mismo_pago_gana_una(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        payment = await RecordPayment(SqlAlchemyPaymentRepository(session))(
            _request(), now=NOW, today=TODAY
        )
        await SqlAlchemyPaymentRepository(session).add_void(
            PaymentVoid(payment_id=payment.id, reason="a", voided_by=uuid4(), voided_at=NOW)
        )

    with pytest.raises(PaymentAlreadyVoidedError):
        async with sessions.begin() as session:
            await SqlAlchemyPaymentRepository(session).add_void(
                PaymentVoid(payment_id=payment.id, reason="b", voided_by=uuid4(), voided_at=NOW)
            )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ledger_payments SET amount_cents = 1",
        "DELETE FROM ledger_payments",
        "UPDATE ledger_payment_voids SET reason = 'x'",
        "DELETE FROM ledger_payment_voids",
        "UPDATE ledger_movements SET amount_cents = 1",
        "DELETE FROM ledger_movements",
        "UPDATE ledger_movement_voids SET reason = 'x'",
        "DELETE FROM ledger_movement_voids",
    ],
)
async def test_regla_5_el_trigger_rechaza_update_y_delete(
    sessions: async_sessionmaker[AsyncSession], statement: str
) -> None:
    clock = FakeLedgerClock()
    async with sessions.begin() as session:
        payments = SqlAlchemyPaymentRepository(session)
        payment = await RecordPayment(payments)(_request(), now=NOW, today=TODAY)
        await VoidPayment(payments)(payment.id, reason="x", voided_by=uuid4(), now=NOW)
        movements = SqlAlchemyMovementRepository(session)
        movement = await RecordMovement(movements, clock)(_movement())
        await VoidMovement(movements, clock)(movement.movement.id, reason="x", voided_by=uuid4())

    with pytest.raises(DBAPIError, match="no se modific"):
        async with sessions.begin() as session:
            await session.execute(text(statement))


async def test_hu21_hu22_filtros_y_sumas_sin_anulados(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    clock, event_id = FakeLedgerClock(), uuid4()
    async with sessions.begin() as session:
        payments = SqlAlchemyPaymentRepository(session)
        movements = SqlAlchemyMovementRepository(session)
        await RecordPayment(payments)(
            _request(PaymentKind.ADVANCE, amount_cents=100_000, paid_on=date(2026, 10, 3)),
            now=NOW,
            today=TODAY,
        )
        voided = await RecordPayment(payments)(_request(amount_cents=7_000), now=NOW, today=TODAY)
        await VoidPayment(payments)(voided.id, reason="x", voided_by=uuid4(), now=NOW)
        await RecordPayment(payments)(
            _request(PaymentKind.REFUND, amount_cents=2_000), now=NOW, today=TODAY
        )
        kept = await RecordMovement(movements, clock)(_movement(event_id=event_id))
        gone = await RecordMovement(movements, clock)(
            _movement(category=MovementCategory.STAFF, event_id=event_id)
        )
        await VoidMovement(movements, clock)(gone.movement.id, reason="x", voided_by=uuid4())
        await RecordMovement(movements, clock)(
            _movement(type=MovementType.INCOME, category=MovementCategory.OTHER_INCOME)
        )

    async with sessions() as session:
        payments = SqlAlchemyPaymentRepository(session)
        movements = SqlAlchemyMovementRepository(session)
        months = await CashTotals(payments, movements)(date(2026, 10, 1), date(2026, 11, 30))
        by_event = await EventCash(movements)(event_id)
        active = await ListMovements(movements)(
            MovementFilters(event_id=event_id, state=MovementState.ACTIVE)
        )
        voided_page = await ListMovements(movements)(MovementFilters(state=MovementState.VOIDED))

    assert [(m.month, m.client_payments_cents, m.refunds_cents) for m in months] == [
        (10, 100_000, 0),
        (11, 0, 2_000),
    ]
    assert months[1].by_category == {
        MovementCategory.SUPPLIES: 30_000,
        MovementCategory.OTHER_INCOME: 30_000,
    }
    assert by_event == {MovementCategory.SUPPLIES: 30_000}
    assert [e.movement.id for e in active.items] == [kept.movement.id]
    assert (voided_page.total, voided_page.items[0].void is not None) == (1, True)
