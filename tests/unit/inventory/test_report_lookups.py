"""Consultas de inventory para los reportes y el panel (CA-32.3, CA-31.10). Sin base de datos."""

from datetime import date
from decimal import Decimal

from local_eventos.modules.inventory.application.use_cases.lookups import (
    ListMovementsBetween,
    ListStock,
)
from local_eventos.modules.inventory.domain.movement import MovementKind
from local_eventos.modules.inventory.domain.product import Category

from .fakes import TODAY
from .world import World


async def test_ca32_3_stock_con_costo_valor_y_alertas() -> None:
    world = World()
    plate = await world.product(min_stock=Decimal(10))
    milk = await world.product(
        "LEC-01", name="Leche", category=Category.BEVERAGES, min_stock=Decimal(1)
    )
    await world.entry(plate, "10", cost=500)
    await world.entry(milk, "4", cost=350, expires_on=date(2026, 12, 5))
    stock = ListStock(world.products, world.views())

    items = {i.product.code: i for i in await stock()}
    drinks = await stock(Category.BEVERAGES)

    assert (items["PLA-01"].stock, items["PLA-01"].value_cents) == (Decimal(10), 5_000)
    assert items["PLA-01"].is_low_stock and not items["LEC-01"].is_low_stock
    assert items["LEC-01"].expiring_soon and items["LEC-01"].category is Category.BEVERAGES
    assert [i.product.code for i in drinks] == ["LEC-01"]


async def test_ca32_3_movimientos_del_rango_con_su_producto() -> None:
    world = World()
    plate = await world.product()
    await world.entry(plate, "10", cost=500, occurred_on=date(2026, 10, 30))
    await world.entry(plate, "5", cost=500)
    await world.move(MovementKind.ADJUSTMENT, plate, "-2", reason="Conteo")
    movements = ListMovementsBetween(world.products, world.movements)

    found = await movements(date(2026, 11, 1), TODAY)
    adjustments = await movements(date(2026, 11, 1), TODAY, MovementKind.ADJUSTMENT)

    assert [(m.kind, m.quantity, m.product.code) for m in found] == [
        (MovementKind.ENTRY, Decimal("5.000"), "PLA-01"),
        (MovementKind.ADJUSTMENT, Decimal("-2.000"), "PLA-01"),
    ]
    assert [m.reason for m in adjustments] == ["Conteo"]
