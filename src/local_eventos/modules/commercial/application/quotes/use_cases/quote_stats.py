"""Consulta de solo lectura: números de cotizaciones para el panel del administrador (HU31).

La usa `reporting` por `commercial.public_api`. Todo sale de datos reales; nada se rellena.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteFilters,
    QuoteRepository,
    QuoteSummary,
)
from local_eventos.modules.commercial.domain.quotes.quote import QuoteStatus

UPCOMING_DAYS = 30
RECENT_LIMIT = 5
_UPCOMING_LIMIT = 50
# Lima es siempre UTC−5 (sin horario de verano): el mes se cuenta en hora de Lima.
_LIMA = timezone(timedelta(hours=-5))


@dataclass(frozen=True)
class QuoteStats:
    year: int
    month: int
    drafts: int  # en borrador y vigentes (CA-31.1)
    sent_pending: int  # enviadas, vigentes, esperando respuesta (CA-31.1)
    created_in_month: int  # CA-31.2
    accepted_in_month: int  # creadas en el mes y hoy aceptadas (spec §5)
    accepted_amount_cents: int
    upcoming: list[QuoteSummary]  # aceptadas con evento en los próximos 30 días (CA-31.3)
    recent: list[QuoteSummary]  # las 5 más recientes (CA-31.4)


class GetQuoteStats:
    def __init__(self, quotes: QuoteRepository, clock: Clock) -> None:
        self._quotes = quotes
        self._clock = clock

    async def __call__(self, year: int | None = None, month: int | None = None) -> QuoteStats:
        today = self._clock.today()
        year, month = (year or today.year), (month or today.month)
        start = datetime.combine(date(year, month, 1), time(), _LIMA)
        end = datetime.combine(_first_of_next_month(year, month), time(), _LIMA)
        in_month = QuoteFilters(created_from=start, created_to=end)
        accepted_in_month = QuoteFilters(
            created_from=start, created_to=end, status=QuoteStatus.ACCEPTED
        )

        upcoming, _ = await self._quotes.search(
            QuoteFilters(
                status=QuoteStatus.ACCEPTED,
                event_date_from=today,
                event_date_to=today + timedelta(days=UPCOMING_DAYS),
            ),
            today=today,
            limit=_UPCOMING_LIMIT,
            offset=0,
        )
        recent, _ = await self._quotes.search(
            QuoteFilters(), today=today, limit=RECENT_LIMIT, offset=0
        )
        return QuoteStats(
            year=year,
            month=month,
            drafts=await self._count(QuoteFilters(status=QuoteStatus.DRAFT), today),
            sent_pending=await self._count(QuoteFilters(status=QuoteStatus.SENT), today),
            created_in_month=await self._count(in_month, today),
            accepted_in_month=await self._count(accepted_in_month, today),
            accepted_amount_cents=await self._quotes.total_amount(accepted_in_month, today=today),
            upcoming=sorted(upcoming, key=lambda q: (q.event_date, q.code)),
            recent=recent,
        )

    async def _count(self, filters: QuoteFilters, today: date) -> int:
        _, total = await self._quotes.search(filters, today=today, limit=1, offset=0)
        return total


def _first_of_next_month(year: int, month: int) -> date:
    return date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
