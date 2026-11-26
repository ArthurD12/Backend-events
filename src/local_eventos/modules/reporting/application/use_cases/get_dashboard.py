"""Caso de uso: armar el panel del administrador (HU31).

`reporting` es el único módulo que junta datos de otros, siempre por su `public_api`:
cotizaciones (CA-31.1 a CA-31.4), próximos eventos (CA-31.7), caja del mes (CA-31.8, mismo
cálculo que el flujo de caja), cobros pendientes (CA-31.9), alertas de almacén (CA-31.10) y
compras abiertas (CA-31.11). Ningún número se inventa: sin datos, 0 o lista vacía.
"""

import calendar
from dataclasses import dataclass
from datetime import date

from local_eventos.modules.commercial.public_api import (
    EventReportItem,
    QuoteStats,
    QuoteStatsLookup,
    Receivables,
    ReceivablesLookup,
    UpcomingEventsLookup,
)
from local_eventos.modules.inventory.public_api import StockReportLookup
from local_eventos.modules.ledger.public_api import CashTotalsLookup
from local_eventos.modules.purchasing.public_api import OpenPurchases, OpenPurchasesLookup
from local_eventos.modules.reporting.application.use_cases.cash_flow import CashSummary

UPCOMING_DAYS = 14  # CA-31.7


@dataclass(frozen=True)
class InventoryAlerts:
    """Productos activos con stock bajo o por vencer (mismo criterio que HU23)."""

    low_stock: int
    expiring_soon: int


@dataclass(frozen=True)
class Dashboard:
    year: int
    month: int
    quotes: QuoteStats
    upcoming_events: list[EventReportItem]
    cash: CashSummary  # del mes elegido
    receivables: Receivables
    inventory: InventoryAlerts
    purchases: OpenPurchases


class GetDashboard:
    def __init__(
        self,
        quote_stats: QuoteStatsLookup,
        cash_totals: CashTotalsLookup,
        upcoming: UpcomingEventsLookup,
        receivables: ReceivablesLookup,
        stock: StockReportLookup,
        open_purchases: OpenPurchasesLookup,
    ) -> None:
        self._quote_stats = quote_stats
        self._cash_totals = cash_totals
        self._upcoming = upcoming
        self._receivables = receivables
        self._stock = stock
        self._open_purchases = open_purchases

    async def __call__(self, year: int | None = None, month: int | None = None) -> Dashboard:
        """Una consulta por bloque, en la misma transacción (sin llamadas en paralelo)."""
        quotes = await self._quote_stats(year, month)
        last_day = calendar.monthrange(quotes.year, quotes.month)[1]
        cash = await self._cash_totals(
            date(quotes.year, quotes.month, 1), date(quotes.year, quotes.month, last_day)
        )
        stock = await self._stock()
        return Dashboard(
            year=quotes.year,
            month=quotes.month,
            quotes=quotes,
            upcoming_events=await self._upcoming(UPCOMING_DAYS),
            cash=CashSummary.of(cash),
            receivables=await self._receivables(),
            inventory=InventoryAlerts(
                low_stock=sum(1 for i in stock if i.is_low_stock),
                expiring_soon=sum(1 for i in stock if i.expiring_soon),
            ),
            purchases=await self._open_purchases(),
        )
