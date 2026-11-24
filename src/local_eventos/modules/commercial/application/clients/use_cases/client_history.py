"""Caso de uso: historial comercial de un cliente (HU05).

Junta sus cotizaciones, contratos y eventos. Solo lectura: no cambia nada.
"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from local_eventos.modules.commercial.application.clients.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.commercial.application.clients.use_cases.get_client import GetClient
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractFilters,
    ContractRepository,
)
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventFilters,
    EventRepository,
)
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteFilters,
    QuoteRepository,
    QuoteSummary,
)
from local_eventos.modules.commercial.domain.clients.client import Client
from local_eventos.modules.commercial.domain.contracts.contract import ContractStatus
from local_eventos.modules.commercial.domain.events.event import EventStatus
from local_eventos.modules.commercial.domain.quotes.quote import EventType, QuoteStatus

_ALL = 10_000  # sin paginar: una MYPE no llega a tantos registros por cliente (spec §7)


@dataclass(frozen=True)
class HistoryEvent:
    id: UUID
    code: str
    event_type: EventType
    event_date: date
    total_cents: int  # el del contrato (CA-05.3)
    status: EventStatus


@dataclass(frozen=True)
class HistorySummary:
    """R-HIS-1."""

    quotes: int
    accepted_quotes: int
    events: int
    contracted_cents: int  # contratos firmados; los anulados no cuentan


@dataclass(frozen=True)
class History:
    client: Client
    quotes: list[QuoteSummary]
    events: list[HistoryEvent]
    summary: HistorySummary


class ClientHistory:
    def __init__(
        self,
        clients: ClientRepository,
        quotes: QuoteRepository,
        contracts: ContractRepository,
        events: EventRepository,
        clock: Clock,
    ) -> None:
        self._clients = clients
        self._quotes = quotes
        self._contracts = contracts
        self._events = events
        self._clock = clock

    async def __call__(self, client_id: UUID) -> History:
        client = await GetClient(self._clients)(client_id)  # 404 si no existe
        quotes, _ = await self._quotes.search(
            QuoteFilters(client_id=client_id), today=self._clock.today(), limit=_ALL, offset=0
        )
        contracts, _ = await self._contracts.search(
            ContractFilters(client_id=client_id), limit=_ALL, offset=0
        )
        events, _ = await self._events.search(
            EventFilters(client_id=client_id), limit=_ALL, offset=0
        )
        totals = {c.id: c.total_cents for c in contracts}
        history_events = [
            HistoryEvent(
                id=e.id,
                code=e.code,
                event_type=e.event_type,
                event_date=e.event_date,
                total_cents=totals.get(e.contract_id, 0),
                status=e.status,
            )
            for e in events
        ]
        # De la fecha de evento más reciente a la más antigua (spec §5).
        quotes.sort(key=lambda q: (q.event_date, q.code), reverse=True)
        history_events.sort(key=lambda e: (e.event_date, e.code), reverse=True)
        return History(
            client=client,
            quotes=quotes,
            events=history_events,
            summary=HistorySummary(
                quotes=len(quotes),
                accepted_quotes=sum(q.status is QuoteStatus.ACCEPTED for q in quotes),
                events=len(history_events),
                contracted_cents=sum(
                    c.total_cents for c in contracts if c.status is ContractStatus.SIGNED
                ),
            ),
        )
