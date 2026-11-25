"""Casos de uso de inventario con piezas en memoria (HU23, HU26)."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from local_eventos.modules.commercial.public_api import EventStatus
from local_eventos.modules.inventory.application.errors import (
    CodeTakenError,
    EventNotAssignableError,
    EventNotFoundError,
    ProductInactiveError,
    ProductNotFoundError,
    ReturnExceedsError,
    WasteExceedsError,
)
from local_eventos.modules.inventory.application.ports.product_repository import ProductFilters
from local_eventos.modules.inventory.application.use_cases.lookups import (
    ListEventMaterials,
    ListLowStock,
    LookupProduct,
)
from local_eventos.modules.inventory.application.use_cases.movements import (
    MovementCommand,
    RecordEntries,
    StockEntry,
)
from local_eventos.modules.inventory.application.use_cases.products import (
    ListProductMovements,
    ProductCommand,
    SetProductActive,
    UpdateProduct,
)
from local_eventos.modules.inventory.domain.errors import InsufficientStockError
from local_eventos.modules.inventory.domain.movement import MovementKind
from local_eventos.modules.inventory.domain.product import Category, ProductKind, Unit

from .world import World

EXIT, RETURN, WASTE = MovementKind.EXIT, MovementKind.RETURN, MovementKind.WASTE


async def test_ca23_1_codigo_repetido_409() -> None:
    world = World()
    await world.product("PLA-01")

    with pytest.raises(CodeTakenError):
        await world.product("pla-01")


async def test_ca23_1_editar_no_puede_tomar_el_codigo_de_otro() -> None:
    world = World()
    await world.product("PLA-01")
    other = await world.product("VAS-01", name="Vaso")
    command = ProductCommand(
        code="PLA-01", name="Vaso", category=Category.GLASSWARE, unit=Unit.UNIT,
        kind=ProductKind.REUSABLE, min_stock=Decimal(0),
    )  # fmt: skip

    with pytest.raises(CodeTakenError):
        await UpdateProduct(world.products)(other.id, command)
    updated = await UpdateProduct(world.products)(other.id, replace(command, code="VAS-02"))
    assert updated.code == "VAS-02" and updated.category is Category.GLASSWARE


async def test_ca23_3_se_desactiva_sin_borrar() -> None:
    world = World()
    plate = await world.product()

    await SetProductActive(world.products)(plate.id, active=False)

    assert world.products.products[plate.id].active is False
    assert await world.list()(ProductFilters()) == []
    assert len(await world.list()(ProductFilters(include_inactive=True))) == 1
    with pytest.raises(ProductNotFoundError):
        await SetProductActive(world.products)(uuid4(), active=True)


async def test_ca23_4_stock_es_la_suma_de_movimientos_e_historial() -> None:
    world = World()
    plate = await world.product()
    event = world.events.add()
    await world.entry(plate, "100", 200)
    await world.move(EXIT, plate, "30", event_id=event)
    await world.move(RETURN, plate, "25", event_id=event)
    await world.move(WASTE, plate, "2", reason="rotos")
    await world.move(MovementKind.ADJUSTMENT, plate, "-1", reason="conteo")

    view = await world.get()(plate.id)
    history = await ListProductMovements(world.products, world.movements)(plate.id, page_size=2)

    assert view.stock == Decimal(92)
    assert view.avg_cost_cents == 200 and view.stock_value_cents == 18400
    assert history.total == 5
    assert [m.kind for m in history.items] == [MovementKind.ADJUSTMENT, WASTE]


async def test_ca23_5_alertas_en_la_lista() -> None:
    world = World()
    plate = await world.product(min_stock=Decimal(10))
    milk = await world.product("LEC-01", name="Leche", min_stock=Decimal(1))
    await world.entry(plate, "10")
    await world.entry(milk, "5", expires_on=date(2026, 12, 5))

    views = {v.product.code: v for v in await world.list()(ProductFilters())}
    alerts = await world.list()(ProductFilters(), alerts_only=True)

    assert views["PLA-01"].is_low_stock and not views["PLA-01"].expiring_soon
    assert views["LEC-01"].expiring_soon and not views["LEC-01"].is_low_stock
    assert views["LEC-01"].next_expiry == date(2026, 12, 5)
    assert len(alerts) == 2


async def test_busqueda_sin_tildes_por_nombre_o_codigo() -> None:
    world = World()
    await world.product("AZU-01", name="Azúcar rubia", kind=ProductKind.CONSUMABLE)
    await world.product()

    assert [v.product.code for v in await world.list()(ProductFilters(text="azucar"))] == ["AZU-01"]
    assert len(await world.list()(ProductFilters(text="pla-"))) == 1


async def test_ca26_1_salida_a_evento_activo_y_queda_asociada() -> None:
    world = World()
    plate = await world.product()
    event = world.events.add(EventStatus.CONFIRMED)
    await world.entry(plate, "50")

    recorded = await world.move(EXIT, plate, "20", event_id=event)

    assert recorded.stock.quantity == Decimal(30)
    assert recorded.movement.event_id == event
    assert recorded.movement.recorded_by == world.user
    assert world.stock.locked[-1] == plate.id


@pytest.mark.parametrize("status", [EventStatus.FINISHED, EventStatus.CANCELLED])
async def test_ca26_1_evento_terminado_o_cancelado_no_recibe_salidas(status: EventStatus) -> None:
    world = World()
    plate = await world.product()
    await world.entry(plate, "50")

    with pytest.raises(EventNotAssignableError):
        await world.move(EXIT, plate, "1", event_id=world.events.add(status))
    with pytest.raises(EventNotFoundError):
        await world.move(EXIT, plate, "1", event_id=uuid4())


async def test_ca26_2_no_sale_mas_que_el_stock() -> None:
    world = World()
    plate = await world.product()
    await world.entry(plate, "5")

    with pytest.raises(InsufficientStockError) as error:
        await world.move(EXIT, plate, "6", event_id=world.events.add())

    assert error.value.available == Decimal(5)
    assert len(world.movements.movements) == 1


async def test_ca26_3_devolucion_no_supera_lo_que_salio_menos_devuelto_y_perdido() -> None:
    world = World()
    plate = await world.product()
    event = world.events.add()
    await world.entry(plate, "100")
    await world.move(EXIT, plate, "10", event_id=event)
    await world.move(WASTE, plate, "2", event_id=event, reason="rotos")
    await world.move(RETURN, plate, "5", event_id=event)

    with pytest.raises(ReturnExceedsError):
        await world.move(RETURN, plate, "4", event_id=event)
    with pytest.raises(WasteExceedsError):
        await world.move(WASTE, plate, "4", event_id=event, reason="rotos")
    with pytest.raises(ReturnExceedsError):
        await world.move(RETURN, plate, "1", event_id=world.events.add())
    await world.move(RETURN, plate, "3", event_id=event)
    assert world.stock.levels[plate.id].quantity == Decimal(98)  # 100 − 10 + 5 + 3


async def test_ca26_4_merma_de_almacen_baja_el_stock_y_pide_motivo() -> None:
    world = World()
    plate = await world.product()
    await world.entry(plate, "10")

    recorded = await world.move(WASTE, plate, "3", reason="se rompieron al lavar")

    assert recorded.stock.quantity == Decimal(7)
    assert recorded.movement.reason == "se rompieron al lavar"


async def test_producto_inactivo_no_recibe_entradas_ni_salidas_pero_si_devoluciones() -> None:
    world = World()
    plate = await world.product()
    event = world.events.add()
    await world.entry(plate, "10")
    await world.move(EXIT, plate, "4", event_id=event)
    await SetProductActive(world.products)(plate.id, active=False)

    with pytest.raises(ProductInactiveError):
        await world.entry(plate, "1")
    with pytest.raises(ProductInactiveError):
        await world.move(EXIT, plate, "1", event_id=event)
    await world.move(RETURN, plate, "4", event_id=event)
    with pytest.raises(ProductNotFoundError):
        await world.record()(
            MovementCommand(kind=EXIT, product_id=uuid4(), quantity=Decimal(1), event_id=event),
            recorded_by=world.user,
        )


async def test_ca26_6_materiales_del_evento_por_producto() -> None:
    world = World()
    plate = await world.product()
    sugar = await world.product("AZU-01", name="Azúcar", kind=ProductKind.CONSUMABLE)
    event = world.events.add()
    await world.entry(plate, "100")
    await world.entry(sugar, "10")
    await world.move(EXIT, plate, "50", event_id=event)
    await world.move(EXIT, sugar, "2.5", event_id=event)
    await world.move(RETURN, plate, "45", event_id=event)
    await world.move(WASTE, plate, "1", event_id=event, reason="roto")

    lines = await world.materials()(event)

    assert [line.product.code for line in lines] == ["AZU-01", "PLA-01"]
    assert lines[0].materials.out == Decimal("2.5") and lines[0].materials.pending_return == 0
    assert lines[1].materials.pending_return == Decimal(4)
    assert world.stock.levels[plate.id].quantity == Decimal(95)  # la merma del evento no resta
    with pytest.raises(EventNotFoundError):
        await world.materials()(uuid4())


async def test_hu14_materiales_del_evento_para_la_ficha() -> None:
    world = World()
    plate = await world.product()
    sugar = await world.product("AZU-01", name="Azúcar", kind=ProductKind.CONSUMABLE)
    event = world.events.add()
    await world.entry(plate, "100")
    await world.entry(sugar, "10")
    await world.move(EXIT, plate, "50", event_id=event)
    await world.move(EXIT, sugar, "2.5", event_id=event)
    await world.move(RETURN, plate, "45", event_id=event)
    await world.move(WASTE, plate, "1", event_id=event, reason="roto")

    lines = await ListEventMaterials(world.products, world.movements)(event)

    assert [(m.product.code, m.out, m.returned, m.wasted, m.pending_return) for m in lines] == [
        ("AZU-01", Decimal("2.5"), 0, 0, 0),
        ("PLA-01", Decimal(50), Decimal(45), Decimal(1), Decimal(4)),
    ]
    assert await ListEventMaterials(world.products, world.movements)(uuid4()) == []


async def test_recibir_varias_entradas_en_orden_de_producto() -> None:
    world = World()
    plate = await world.product()
    sugar = await world.product("AZU-01", name="Azúcar", kind=ProductKind.CONSUMABLE)
    purchase = uuid4()
    commands = [
        StockEntry(product_id=p.id, quantity=Decimal(5), unit_cost_cents=100, purchase_id=purchase)
        for p in (plate, sugar)
    ]

    recorded = await RecordEntries(world.record())(commands, recorded_by=world.user)

    assert world.stock.locked == sorted([plate.id, sugar.id], key=str)
    assert {r.movement.purchase_id for r in recorded} == {purchase}


async def test_faltantes_y_consulta_de_producto() -> None:
    world = World()
    plate = await world.product(min_stock=Decimal(10))
    await world.product("AZU-01", name="Azúcar", min_stock=Decimal(0))
    await world.entry(plate, "4")

    low = await ListLowStock(world.products, world.stock)()
    info = await LookupProduct(world.products)(plate.id)

    assert [(i.product.code, i.shortage) for i in low] == [("PLA-01", Decimal(6))]
    assert info is not None and info.code == "PLA-01" and info.active
    assert await LookupProduct(world.products)(uuid4()) is None
