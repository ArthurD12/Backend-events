"""Inventario contra PostgreSQL real (017: HU23, HU26). Necesita Docker.

Prueba lo que solo la base puede garantizar: dos salidas simultáneas no dejan el stock
negativo (bloqueo `FOR UPDATE` + CHECK), los movimientos no se editan ni se borran, y el stock
guardado es la suma de los movimientos.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.inventory.application.errors import CodeTakenError
from local_eventos.modules.inventory.application.ports.product_repository import ProductFilters
from local_eventos.modules.inventory.application.use_cases.movements import (
    MovementCommand,
    RecordMovement,
)
from local_eventos.modules.inventory.domain.errors import InsufficientStockError
from local_eventos.modules.inventory.domain.movement import MovementKind
from local_eventos.modules.inventory.domain.product import Category, Product, ProductKind, Unit
from local_eventos.modules.inventory.domain.stock import StockLevel
from local_eventos.modules.inventory.infrastructure.product_repository import (
    SqlAlchemyProductRepository,
)
from local_eventos.modules.inventory.infrastructure.stock_repository import (
    SqlAlchemyMovementRepository,
    SqlAlchemyStockRepository,
)
from local_eventos.shared.infrastructure.db import create_engine
from tests.unit.inventory.fakes import FakeClock, FakeEventLookup

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
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
        # TRUNCATE no dispara el trigger de UPDATE/DELETE: solo se usa para limpiar las pruebas.
        await connection.execute(
            text("TRUNCATE inventory_stock, inventory_movements, inventory_products")
        )
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


class SlowStock(SqlAlchemyStockRepository):
    """Espera tras bloquear: sin `FOR UPDATE`, las dos salidas leerían el mismo stock."""

    async def lock(self, product_id: UUID) -> StockLevel:
        level = await super().lock(product_id)
        await asyncio.sleep(0.3)
        return level


EVENTS = FakeEventLookup()
EVENT = EVENTS.add()


def _recorder(session: AsyncSession, *, slow: bool = False) -> RecordMovement:
    stock = (SlowStock if slow else SqlAlchemyStockRepository)(session)
    return RecordMovement(
        SqlAlchemyProductRepository(session),
        stock,
        SqlAlchemyMovementRepository(session),
        EVENTS,
        FakeClock(),
    )


async def _product(sessions: async_sessionmaker[AsyncSession], code: str = "PLA-01") -> Product:
    product = Product.create(
        code=code, name="Plato llano", category=Category.DINNERWARE, unit=Unit.UNIT,
        kind=ProductKind.REUSABLE, min_stock=Decimal(10),
    )  # fmt: skip
    async with sessions.begin() as session:
        await SqlAlchemyProductRepository(session).add(product)
    return product


async def _move(
    sessions: async_sessionmaker[AsyncSession], command: MovementCommand, *, slow: bool = False
) -> None:
    async with sessions.begin() as session:
        await _recorder(session, slow=slow)(command, recorded_by=USER)


def _entry(product: Product, quantity: str, cost: int = 100, **extra: object) -> MovementCommand:
    return MovementCommand(
        kind=MovementKind.ENTRY, product_id=product.id, quantity=Decimal(quantity),
        unit_cost_cents=cost, **extra,  # type: ignore[arg-type]
    )  # fmt: skip


def _exit(product: Product, quantity: str) -> MovementCommand:
    return MovementCommand(
        kind=MovementKind.EXIT, product_id=product.id, quantity=Decimal(quantity), event_id=EVENT
    )


async def test_rn20_dos_salidas_simultaneas_no_dejan_stock_negativo(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    product = await _product(sessions)
    await _move(sessions, _entry(product, "10"))

    results = await asyncio.gather(
        _move(sessions, _exit(product, "6"), slow=True),
        _move(sessions, _exit(product, "6"), slow=True),
        return_exceptions=True,
    )

    assert sorted(type(r).__name__ for r in results) == ["InsufficientStockError", "NoneType"]
    failed = next(r for r in results if isinstance(r, InsufficientStockError))
    assert failed.available == Decimal(4)
    async with sessions() as session:
        levels = await SqlAlchemyStockRepository(session).get_many([product.id])
        exits, total = await SqlAlchemyMovementRepository(session).list_for_product(
            product.id, limit=10, offset=0
        )
    assert levels[product.id].quantity == Decimal("4.000")
    assert total == 2


async def test_check_de_la_base_impide_stock_negativo(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    product = await _product(sessions)

    with pytest.raises(IntegrityError, match="ck_inventory_stock_quantity_not_negative"):
        async with sessions.begin() as session:
            await session.execute(
                text("INSERT INTO inventory_stock VALUES (:id, -1, 0)"), {"id": product.id}
            )


async def test_r_inv_5_movimientos_no_se_modifican_ni_se_borran(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    product = await _product(sessions)
    await _move(sessions, _entry(product, "5"))

    for statement in (
        "UPDATE inventory_movements SET quantity = 50",
        "DELETE FROM inventory_movements",
    ):
        with pytest.raises(DBAPIError, match="no se modifican ni se borran"):
            async with sessions.begin() as session:
                await session.execute(text(statement))


async def test_ca23_4_stock_guardado_es_la_suma_de_los_movimientos(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    plate = await _product(sessions)
    await _move(sessions, _entry(plate, "100", 200, lot="L-1", expires_on=date(2027, 1, 1)))
    await _move(sessions, _entry(plate, "50.5", 300))
    await _move(sessions, _exit(plate, "30.25"))
    returned = MovementCommand(
        kind=MovementKind.RETURN, product_id=plate.id, quantity=Decimal(20), event_id=EVENT
    )
    await _move(sessions, returned)
    for kind, quantity, event in (
        (MovementKind.WASTE, "2", None),
        (MovementKind.WASTE, "3", EVENT),  # merma del evento: no cambia el stock
        (MovementKind.ADJUSTMENT, "-1.125", None),
    ):
        await _move(
            sessions,
            MovementCommand(
                kind=kind,
                product_id=plate.id,
                quantity=Decimal(quantity),
                event_id=event,
                reason="conteo",
            ),  # fmt: skip
        )

    async with sessions() as session:
        stored = await session.scalar(
            text("SELECT quantity FROM inventory_stock WHERE product_id = :id"), {"id": plate.id}
        )
        summed = await session.scalar(
            text(
                "SELECT SUM(CASE WHEN kind IN ('ENTRY', 'RETURN', 'ADJUSTMENT') THEN quantity"
                " WHEN kind = 'WASTE' AND event_id IS NOT NULL THEN 0 ELSE -quantity END)"
                " FROM inventory_movements WHERE product_id = :id"
            ),
            {"id": plate.id},
        )
        level = (await SqlAlchemyStockRepository(session).get_many([plate.id]))[plate.id]
        entries = await SqlAlchemyMovementRepository(session).entries_for([plate.id])
        event_moves = await SqlAlchemyMovementRepository(session).list_for_event(EVENT, plate.id)
    assert stored == summed == Decimal("137.125")
    assert level.avg_cost_cents == 234  # (100×200 + 50.5×300) / 150.5
    assert {e.lot for e in entries} == {"L-1", None}
    # El reloj de prueba da la misma hora a todos: se compara sin orden.
    assert sorted(m.kind for m in event_moves) == ["EXIT", "RETURN", "WASTE"]


async def test_productos_codigo_unico_y_busqueda_sin_tildes(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _product(sessions, "PLA-01")
    sugar = Product.create(
        code="AZU-01", name="Azúcar rubia", category=Category.SUPPLIES, unit=Unit.KG,
        kind=ProductKind.CONSUMABLE, min_stock=Decimal("2.5"),
    )  # fmt: skip
    async with sessions.begin() as session:
        await SqlAlchemyProductRepository(session).add(sugar)

    with pytest.raises(CodeTakenError):
        await _product(sessions, "PLA-01")
    async with sessions() as session:
        repo = SqlAlchemyProductRepository(session)
        by_name = await repo.search(ProductFilters(text="azucar"), limit=10)
        by_code = await repo.search(ProductFilters(text="pla-"), limit=10)
        by_category = await repo.search(ProductFilters(category=Category.SUPPLIES), limit=10)
    assert [p.code for p in by_name] == ["AZU-01"]
    assert [p.code for p in by_code] == ["PLA-01"]
    assert by_category[0].min_stock == Decimal("2.500")
