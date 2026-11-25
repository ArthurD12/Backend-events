"""Reportes (HU32–HU34) con consultas falsas: filtros, filas, totales y montos ocultos."""

from datetime import date

import pytest

from local_eventos.modules.commercial.public_api import EventStatus
from local_eventos.modules.inventory.public_api import Category
from local_eventos.modules.reporting.application.errors import (
    ReportRangeInvalidError,
    ReportUnavailableError,
)
from local_eventos.modules.reporting.application.reports.cash import GetCashReport
from local_eventos.modules.reporting.application.reports.events import GetEventsReport
from local_eventos.modules.reporting.application.reports.inventory import (
    GetInventoryMovementsReport,
    GetStockReport,
)
from local_eventos.modules.reporting.application.reports.purchases import GetPurchasesReport
from local_eventos.modules.reporting.application.reports.staff import GetStaffReport
from local_eventos.modules.reporting.application.reports.table import Column, ReportTable

from .report_fakes import (
    NOW,
    FakeEvents,
    FixedClock,
    cash_entries,
    event_refs,
    movements,
    purchases,
    stock,
)

NOV_1, NOV_30 = date(2026, 11, 1), date(2026, 11, 30)


def _totals(table: ReportTable) -> dict[str, object]:
    return {t.key: t.value for t in table.totals}


def _column(table: ReportTable, key: str) -> list[object]:
    index = [c.key for c in table.columns].index(key)
    return [row[index] for row in table.rows]


async def test_ca32_1_eventos_con_montos_filtros_y_totales() -> None:
    events = FakeEvents()

    table = await GetEventsReport(events, FixedClock())(
        NOV_1, NOV_30, status=EventStatus.SCHEDULED, include_amounts=True
    )

    assert table.generated_at == NOW
    assert [(f.label, f.value) for f in table.filters] == [
        ("Desde", "01/11/2026"), ("Hasta", "30/11/2026"), ("Estado", "Programado")
    ]  # fmt: skip
    assert table.rows[0][:6] == (
        "EVT-2026-0001", date(2026, 12, 19), "José Ramírez", "Matrimonio", 120, "Programado"
    )  # fmt: skip
    assert _totals(table) == {
        "events": 2, "guests": 240, "total": 1_200_000, "paid": 1_000_000, "balance": 200_000
    }  # fmt: skip
    assert events.filters[0].status is EventStatus.SCHEDULED
    assert table.notes == ()


async def test_ca32_1_sin_permiso_de_pagos_los_montos_van_vacios() -> None:
    table = await GetEventsReport(FakeEvents(), FixedClock())(NOV_1, NOV_30, include_amounts=False)

    assert _column(table, "total") == _column(table, "paid") == _column(table, "balance") == [
        None, None
    ]  # fmt: skip
    totals = _totals(table)
    assert (totals["total"], totals["paid"], totals["balance"], totals["events"]) == (
        None, None, None, 2
    )  # fmt: skip
    assert table.notes


@pytest.mark.parametrize(
    ("date_from", "date_to"),
    [(NOV_30, NOV_1), (date(2026, 1, 1), date(2027, 1, 2))],
)
async def test_r_rep_2_rango_invalido(date_from: date, date_to: date) -> None:
    with pytest.raises(ReportRangeInvalidError):
        await GetEventsReport(FakeEvents(), FixedClock())(date_from, date_to, include_amounts=True)
    with pytest.raises(ReportRangeInvalidError):
        await GetCashReport(cash_entries, event_refs, FixedClock())(date_from, date_to)


async def test_r_rep_2_hasta_366_dias() -> None:
    table = await GetCashReport(cash_entries, event_refs, FixedClock())(
        date(2028, 1, 1), date(2028, 12, 31)
    )

    assert table.rows


async def test_ca32_2_caja_lista_anulados_pero_no_los_suma() -> None:
    table = await GetCashReport(cash_entries, event_refs, FixedClock())(NOV_1, NOV_30)

    assert [(r[1], r[3], r[4], r[6]) for r in table.rows] == [
        ("Pago de cliente", "Adelanto PAG-2026-0001", "EVT-2026-0001", False),
        ("Pago de cliente", "Adelanto PAG-2026-0001", "EVT-2026-0001", True),
        ("Devolución", "Devolución PAG-2026-0001", "EVT-2026-0001", False),
        ("Ingreso", "Mozos", "EVT-2026-0001", False),
        ("Egreso", "Mozos", "EVT-2026-0001", False),
    ]
    assert _totals(table) == {
        "client_payments": 500_000, "refunds": 10_000, "other_income": 30_000,
        "income": 520_000, "expenses": 120_000, "net": 400_000,
    }  # fmt: skip


async def test_ca32_3_stock_y_movimientos() -> None:
    stock_table = await GetStockReport(stock, FixedClock())(Category.DINNERWARE)
    moves = await GetInventoryMovementsReport(movements, event_refs, FixedClock())(NOV_1, NOV_30)

    assert [(f.label, f.value) for f in stock_table.filters] == [("Categoría", "Vajilla")]
    assert stock_table.rows[0][:4] == ("PLA-01", "Plato llano", "Vajilla", "Unidad")
    assert _totals(stock_table) == {
        "products": 2, "value": 5_575, "low_stock": 1, "expiring_soon": 1
    }  # fmt: skip
    assert _column(moves, "event") == [None, "EVT-2026-0001"]
    assert _column(moves, "kind") == ["Entrada", "Salida"]
    assert _totals(moves) == {"movements": 2, "entries_value": 5_000}


async def test_ca32_4_compras_sin_sumar_canceladas() -> None:
    table = await GetPurchasesReport(purchases, event_refs, FixedClock())(NOV_1, NOV_30)

    assert _column(table, "status") == ["Recibida", "Cancelada"]
    assert _column(table, "event") == ["EVT-2026-0001", None]
    assert _totals(table) == {"purchases": 2, "total": 4_000}


async def test_ca32_5_personal_no_disponible_sin_consulta_de_staff() -> None:
    with pytest.raises(ReportUnavailableError) as raised:
        await GetStaffReport(None, FixedClock())()

    assert raised.value.code == "report.unavailable"


def test_cada_fila_tiene_una_celda_por_columna() -> None:
    with pytest.raises(ValueError):
        ReportTable("x", "X", NOW, (), (Column("a", "A"),), (("1", "2"),), ())
