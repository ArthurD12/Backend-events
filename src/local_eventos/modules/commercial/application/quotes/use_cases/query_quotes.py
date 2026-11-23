"""Casos de uso: ver una cotización, buscarlas y cambiar su estado (HU08)."""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.commercial.application.quotes.errors import QuoteNotFoundError
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteFilters,
    QuoteRepository,
    QuoteSummary,
)
from local_eventos.modules.commercial.domain.quotes.quote import Quote, QuoteStatus

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class QuotePage:
    items: list[QuoteSummary]
    total: int
    page: int
    page_size: int


class GetQuote:
    def __init__(self, quotes: QuoteRepository) -> None:
        self._quotes = quotes

    async def __call__(self, quote_id: UUID) -> Quote:
        quote = await self._quotes.get(quote_id)
        if quote is None:
            raise QuoteNotFoundError()
        return quote


class SearchQuotes:
    """Busca por código, cliente, fecha del evento y estado (CA-08.5)."""

    def __init__(self, quotes: QuoteRepository, clock: Clock) -> None:
        self._quotes = quotes
        self._clock = clock

    async def __call__(
        self, filters: QuoteFilters, *, page: int = 1, page_size: int = 20
    ) -> QuotePage:
        page = max(page, 1)
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        clean = QuoteFilters(
            text=" ".join(filters.text.split()),
            client_id=filters.client_id,
            status=filters.status,
            event_date_from=filters.event_date_from,
            event_date_to=filters.event_date_to,
        )
        items, total = await self._quotes.search(
            clean, today=self._clock.today(), limit=page_size, offset=(page - 1) * page_size
        )
        return QuotePage(items=items, total=total, page=page, page_size=page_size)


class ChangeQuoteStatus:
    """Enviada, aceptada, rechazada o de vuelta a borrador, según R-COT-3 (CA-08.2)."""

    def __init__(self, quotes: QuoteRepository, clock: Clock) -> None:
        self._quotes = quotes
        self._clock = clock

    async def __call__(self, quote_id: UUID, status: QuoteStatus) -> Quote:
        quote = await self._quotes.get(quote_id)
        if quote is None:
            raise QuoteNotFoundError()
        quote.change_status(status, self._clock.today())
        await self._quotes.update(quote)
        return quote
