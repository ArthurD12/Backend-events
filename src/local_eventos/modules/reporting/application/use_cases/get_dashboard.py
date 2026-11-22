"""Caso de uso: armar el panel del administrador (HU31, primera parte).

`reporting` es el único módulo que junta datos de otros, siempre por su `public_api`. Hoy solo
hay cotizaciones; caja y stock se sumarán aquí cuando existan esos módulos (spec §6).
"""

from dataclasses import dataclass

from local_eventos.modules.commercial.public_api import QuoteStats, QuoteStatsLookup


@dataclass(frozen=True)
class Dashboard:
    year: int
    month: int
    quotes: QuoteStats


class GetDashboard:
    def __init__(self, quote_stats: QuoteStatsLookup) -> None:
        self._quote_stats = quote_stats

    async def __call__(self, year: int | None = None, month: int | None = None) -> Dashboard:
        quotes = await self._quote_stats(year, month)
        return Dashboard(year=quotes.year, month=quotes.month, quotes=quotes)
