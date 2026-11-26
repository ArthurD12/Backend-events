"""Panel del administrador ampliado (CA-31.7 a CA-31.11) con consultas falsas."""

from datetime import date

from local_eventos.modules.commercial.public_api import QuoteStats
from local_eventos.modules.inventory.public_api import Category, StockItem
from local_eventos.modules.ledger.public_api import MonthlyCash, MovementCategory
from local_eventos.modules.purchasing.public_api import OpenPurchases
from local_eventos.modules.reporting.application.use_cases.get_dashboard import (
    GetDashboard,
    InventoryAlerts,
)

from .report_fakes import open_purchases, receivables, stock, upcoming

CASH_CALLS: list[tuple[date, date]] = []


async def quote_stats(year: int | None = None, month: int | None = None) -> QuoteStats:
    return QuoteStats(
        year=year or 2026, month=month or 11, drafts=0, sent_pending=0, created_in_month=0,
        accepted_in_month=0, accepted_amount_cents=0, upcoming=[], recent=[],
    )  # fmt: skip


async def cash(date_from: date, date_to: date) -> list[MonthlyCash]:
    CASH_CALLS.append((date_from, date_to))
    return [MonthlyCash(2026, 2, 300_000, 10_000, {MovementCategory.SUPPLIES: 50_000})]


async def no_cash(date_from: date, date_to: date) -> list[MonthlyCash]:
    return []


async def no_stock(
    category: Category | None = None, *, include_inactive: bool = False
) -> list[StockItem]:
    return []


async def no_upcoming(days: int = 14) -> list:  # type: ignore[type-arg]
    return []


async def test_ca31_7_a_31_11_bloques_del_panel() -> None:
    CASH_CALLS.clear()
    use_case = GetDashboard(quote_stats, cash, upcoming, receivables, stock, open_purchases)

    dashboard = await use_case(2026, 2)

    assert [(date(2026, 2, 1), date(2026, 2, 28))] == CASH_CALLS
    assert (dashboard.cash.income_cents, dashboard.cash.expense_cents) == (290_000, 50_000)
    assert dashboard.cash.net_cents == 240_000
    assert [e.code for e in dashboard.upcoming_events] == ["EVT-2026-0001"]
    assert dashboard.receivables.overdue_contracts == 1
    assert dashboard.inventory == InventoryAlerts(low_stock=1, expiring_soon=1)
    assert dashboard.purchases.total == 3


async def test_panel_sin_datos_muestra_ceros() -> None:
    async def none_open() -> OpenPurchases:
        return OpenPurchases(0, 0)

    dashboard = await GetDashboard(quote_stats, no_cash, no_upcoming, receivables, no_stock,
                                   none_open)()  # fmt: skip

    assert dashboard.cash.net_cents == 0 and dashboard.upcoming_events == []
    assert dashboard.inventory == InventoryAlerts(0, 0)
    assert dashboard.purchases.total == 0
