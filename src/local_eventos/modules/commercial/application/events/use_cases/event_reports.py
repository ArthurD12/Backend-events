"""Consultas de solo lectura de eventos y cobros para `reporting` (HU31–HU34).

`commercial` sabe qué contrato tiene cada evento y cómo se calcula su saldo (RN15); los pagos
los suma `ledger` en una sola consulta para todos los contratos (sin una consulta por evento).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractRepository,
)
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventFilters,
    EventRepository,
    EventSummary,
)
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.domain.contracts.contract import (
    ContractBalance,
    ContractStatus,
)
from local_eventos.modules.commercial.domain.events.event import EventStatus
from local_eventos.modules.commercial.domain.quotes.quote import EventType
from local_eventos.modules.ledger.public_api import ContractPaidTotalsLookup

MAX_REPORT_EVENTS = 5_000  # un año de una MYPE no llega a tanto
_NOT_UPCOMING = (EventStatus.CANCELLED, EventStatus.FINISHED)


@dataclass(frozen=True)
class EventReportFilters:
    date_from: date | None = None  # por fecha del evento
    date_to: date | None = None
    status: EventStatus | None = None
    client_id: UUID | None = None


@dataclass(frozen=True)
class EventReportItem:
    """Un evento con lo contratado, lo pagado (neto de devoluciones) y el saldo (CA-32.1)."""

    id: UUID
    code: str
    event_date: date
    client_name: str
    event_type: EventType
    guests: int
    status: EventStatus
    contract_id: UUID
    total_cents: int
    paid_cents: int
    balance_cents: int
    overdue: bool  # saldo vencido (R-PAG-2)


class ListEventReport:
    def __init__(
        self,
        events: EventRepository,
        contracts: ContractRepository,
        paid_totals: ContractPaidTotalsLookup,
        clock: Clock,
    ) -> None:
        self._events = events
        self._contracts = contracts
        self._paid_totals = paid_totals
        self._clock = clock

    async def __call__(self, filters: EventReportFilters) -> list[EventReportItem]:
        """De la fecha más próxima a la más lejana."""
        summaries, _ = await self._events.search(
            EventFilters(
                status=filters.status,
                client_id=filters.client_id,
                date_from=filters.date_from,
                date_to=filters.date_to,
            ),
            limit=MAX_REPORT_EVENTS,
            offset=0,
        )
        return await self._items(summaries)

    async def _items(self, summaries: list[EventSummary]) -> list[EventReportItem]:
        contract_ids = [s.contract_id for s in summaries]
        contracts = {c.id: c for c in await self._contracts.get_many(contract_ids)}
        totals = await self._paid_totals(contract_ids)
        today = self._clock.today()
        items = []
        for summary in summaries:
            contract = contracts.get(summary.contract_id)
            if contract is None:  # la base lo impide con una FK
                continue
            paid = totals[contract.id]
            balance = ContractBalance.of(
                contract, paid_cents=paid.paid_cents, refunded_cents=paid.refunded_cents
            )
            items.append(
                EventReportItem(
                    id=summary.id,
                    code=summary.code,
                    event_date=summary.event_date,
                    client_name=summary.client_name,
                    event_type=summary.event_type,
                    guests=summary.guests,
                    status=summary.status,
                    contract_id=contract.id,
                    total_cents=balance.total_cents,
                    paid_cents=balance.paid_cents - balance.refunded_cents,
                    balance_cents=balance.balance_cents,
                    overdue=balance.is_overdue(today),
                )
            )
        return items


class ListUpcomingEvents:
    """Próximos eventos (CA-31.7): de hoy a `days` días, sin cancelados ni finalizados."""

    def __init__(self, report: ListEventReport, clock: Clock) -> None:
        self._report = report
        self._clock = clock

    async def __call__(self, days: int = 14) -> list[EventReportItem]:
        today = self._clock.today()
        items = await self._report(
            EventReportFilters(date_from=today, date_to=today + timedelta(days=days))
        )
        return [item for item in items if item.status not in _NOT_UPCOMING]


@dataclass(frozen=True)
class Receivables:
    """Cobros pendientes (CA-31.9): contratos firmados con saldo y cuántos están vencidos."""

    total_cents: int
    contracts: int
    overdue_contracts: int
    overdue_cents: int


class GetReceivables:
    def __init__(
        self, contracts: ContractRepository, paid_totals: ContractPaidTotalsLookup, clock: Clock
    ) -> None:
        self._contracts = contracts
        self._paid_totals = paid_totals
        self._clock = clock

    async def __call__(self) -> Receivables:
        signed = await self._contracts.list_by_status(ContractStatus.SIGNED)
        totals = await self._paid_totals([c.id for c in signed])
        today = self._clock.today()
        balances = [
            ContractBalance.of(
                c, paid_cents=totals[c.id].paid_cents, refunded_cents=totals[c.id].refunded_cents
            )
            for c in signed
        ]
        pending = [b for b in balances if b.balance_cents > 0]
        overdue = [b for b in pending if b.is_overdue(today)]
        return Receivables(
            total_cents=sum(b.balance_cents for b in pending),
            contracts=len(pending),
            overdue_contracts=len(overdue),
            overdue_cents=sum(b.balance_cents for b in overdue),
        )


@dataclass(frozen=True)
class EventRefs:
    """Cómo nombrar un evento en un reporte: por su ID o por el de su contrato.

    `by_contract` da el código del evento y, si el contrato aún no es evento, el del contrato.
    """

    by_event: dict[UUID, str]
    by_contract: dict[UUID, str]


class LookupEventRefs:
    def __init__(self, events: EventRepository, contracts: ContractRepository) -> None:
        self._events = events
        self._contracts = contracts

    async def __call__(self, event_ids: list[UUID], contract_ids: list[UUID]) -> EventRefs:
        event_ids = list(dict.fromkeys(event_ids))
        contract_ids = list(dict.fromkeys(contract_ids))
        by_contract = {c.id: c.code for c in await self._contracts.get_many(contract_ids)}
        by_contract.update(await self._events.codes_by_contract(contract_ids))
        return EventRefs(by_event=await self._events.codes(event_ids), by_contract=by_contract)
