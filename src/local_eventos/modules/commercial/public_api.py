"""Superficie pública del módulo commercial: única vía de uso por otros módulos.

Agrupa clientes, cotizaciones, contratos y eventos (ADR 0003). Otro módulo (por ejemplo,
ledger o assistant) importa solo desde aquí, nunca desde sus capas internas (AGENTS.md, regla 3).
"""

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial import composition
from local_eventos.modules.commercial.application.clients.use_cases.get_client_summary import (
    ClientSummary,
)
from local_eventos.modules.commercial.application.events.use_cases.events import (
    EventInfo,
    LookupEvent,
)
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteSummary,
)
from local_eventos.modules.commercial.application.quotes.use_cases.quote_stats import (
    GetQuoteStats,
    QuoteStats,
)
from local_eventos.modules.commercial.domain.events.event import EventStatus


class ClientLookup(Protocol):
    """Busca un cliente por su ID. Devuelve `None` si no existe."""

    async def __call__(self, client_id: UUID) -> ClientSummary | None: ...


class QuoteStatsLookup(Protocol):
    """Números de cotizaciones del mes indicado (por defecto, el actual en Lima)."""

    async def __call__(self, year: int | None = None, month: int | None = None) -> QuoteStats: ...


def quote_stats(session: AsyncSession) -> QuoteStatsLookup:
    """Consulta de solo lectura para el panel (HU31), dentro de la transacción de la petición."""
    return GetQuoteStats(composition.quote_repository(session), composition.clock())


class EventLookup(Protocol):
    """Busca un evento por su ID. Devuelve `None` si no existe."""

    async def __call__(self, event_id: UUID) -> EventInfo | None: ...


def event_lookup(session: AsyncSession) -> EventLookup:
    """Consulta de solo lectura para `staff` (HU17), dentro de la transacción de la petición."""
    return LookupEvent(composition.event_repository(session))


__all__ = [
    "ClientLookup",
    "ClientSummary",
    "EventInfo",
    "EventLookup",
    "EventStatus",
    "QuoteStats",
    "QuoteStatsLookup",
    "QuoteSummary",
    "event_lookup",
    "quote_stats",
]
