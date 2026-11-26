"""Consultas de purchasing para el reporte y el panel (CA-32.4, CA-31.11). Sin base de datos."""

from datetime import date
from decimal import Decimal

from local_eventos.modules.purchasing.application.use_cases.reports import (
    CountOpenPurchases,
    ListPurchaseReport,
    OpenPurchases,
)
from local_eventos.modules.purchasing.domain.purchase import PurchaseStatus, ReceivedLine

from .test_use_cases import USER, World


async def test_ca32_4_compras_del_rango_con_proveedor_total_y_recepcion() -> None:
    world = World()
    sugar = world.inventory.add("AZU-01")
    supplier = await world.supplier()
    requested = await world.request((sugar, "3"))
    received = await world.order(await world.request((sugar, "10")), supplier, 400)
    await world.receive()(received.id, lines=[ReceivedLine(sugar, Decimal(10))], received_by=USER)
    report = ListPurchaseReport(world.purchases, world.suppliers)

    items = await report(date(2026, 11, 25), date(2026, 11, 25))
    only_received = await report(date(2026, 11, 1), date(2026, 11, 30), PurchaseStatus.RECEIVED)
    before = await report(date(2026, 11, 1), date(2026, 11, 24))

    assert [(i.code, i.supplier_name, i.total_cents, i.status) for i in items] == [
        (requested.code, None, None, PurchaseStatus.REQUESTED),
        (received.code, "Distribuidora Lima", 4_000, PurchaseStatus.RECEIVED),
    ]
    assert items[1].received_on == items[1].created_on == date(2026, 11, 25)
    assert [i.code for i in only_received] == [received.code]
    assert before == []


async def test_ca31_11_compras_abiertas() -> None:
    world = World()
    sugar = world.inventory.add("AZU-01")
    supplier = await world.supplier()
    await world.request((sugar, "3"))
    await world.order(await world.request((sugar, "1")), supplier)

    assert await CountOpenPurchases(world.purchases)() == OpenPurchases(requested=1, ordered=1)
