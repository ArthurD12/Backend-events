"""Consultas de solo lectura para la ficha consolidada del evento (HU14, 019).

`reporting` arma la ficha; aquí `commercial` entrega copias (nunca entidades) del evento con su
cliente y servicios, del seguimiento (HU13) y de la cuenta del contrato (HU19).
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from uuid import UUID

from local_eventos.modules.commercial.application.clients.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.commercial.application.clients.use_cases.get_client_summary import (
    ClientSummary,
    GetClientSummary,
)
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractRepository,
)
from local_eventos.modules.commercial.application.contracts.use_cases.payments import account_of
from local_eventos.modules.commercial.application.events.ports.event_log_repository import (
    EventLogRepository,
)
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventRepository,
)
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.domain.contracts.contract import ContractStatus
from local_eventos.modules.commercial.domain.events.activity import ActivityStatus
from local_eventos.modules.commercial.domain.events.event import EventStatus
from local_eventos.modules.commercial.domain.quotes.quote import EventType, LineKind, LineUnit
from local_eventos.modules.ledger.public_api import (
    PaymentEntriesLookup,
    PaymentKind,
    PaymentMethod,
)

RECENT_NOTES = 5


@dataclass(frozen=True)
class EventServiceInfo:
    """Servicio contratado, sin precios (CA-14.2)."""

    kind: LineKind
    service_id: UUID | None
    description: str
    unit: LineUnit
    quantity: int


@dataclass(frozen=True)
class EventDetail:
    """Evento con su cliente y servicios (CA-14.1, CA-14.2)."""

    id: UUID
    code: str
    status: EventStatus
    event_type: EventType
    event_date: date
    start_time: time
    end_time: time
    ends_next_day: bool
    venue: str
    guests: int
    coordinator_id: UUID
    contract_id: UUID
    client: ClientSummary
    services: tuple[EventServiceInfo, ...]


class GetEventDetail:
    def __init__(self, events: EventRepository, clients: ClientRepository) -> None:
        self._events = events
        self._clients = clients

    async def __call__(self, event_id: UUID) -> EventDetail | None:
        event = await self._events.get(event_id)
        if event is None:
            return None
        client = await GetClientSummary(self._clients)(event.client_id)
        if client is None:  # la base lo impide con una FK; solo por si acaso
            return None
        return EventDetail(
            id=event.id,
            code=event.code,
            status=event.status,
            event_type=event.event_type,
            event_date=event.event_date,
            start_time=event.start_time,
            end_time=event.end_time,
            ends_next_day=event.ends_next_day,
            venue=event.venue,
            guests=event.guests,
            coordinator_id=event.coordinator_id,
            contract_id=event.contract_id,
            client=client,
            services=tuple(
                EventServiceInfo(s.kind, s.service_id, s.description, s.unit, s.quantity)
                for s in event.services
            ),
        )


@dataclass(frozen=True)
class ActivityInfo:
    id: UUID
    description: str
    status: ActivityStatus
    responsible_id: UUID
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True)
class NoteInfo:
    id: UUID
    text: str
    created_by: UUID
    created_at: datetime
    edited_at: datetime | None


@dataclass(frozen=True)
class EventFollowUp:
    """CA-14.6: actividades por orden de creación y las últimas observaciones."""

    activities: list[ActivityInfo]
    recent_notes: list[NoteInfo]


class GetEventFollowUp:
    def __init__(self, log: EventLogRepository) -> None:
        self._log = log

    async def __call__(self, event_id: UUID, *, notes_limit: int = RECENT_NOTES) -> EventFollowUp:
        """No revisa que el evento exista: quien la usa ya lo hizo."""
        activities = await self._log.list_activities(event_id)
        notes = await self._log.list_notes(event_id)  # de la más reciente a la más antigua
        return EventFollowUp(
            activities=[
                ActivityInfo(
                    a.id, a.description, a.status, a.responsible_id, a.created_at, a.completed_at
                )  # fmt: skip
                for a in activities
            ],
            recent_notes=[
                NoteInfo(n.id, n.text, n.created_by, n.created_at, n.edited_at)
                for n in notes[:notes_limit]
            ],
        )


@dataclass(frozen=True)
class AccountPaymentInfo:
    id: UUID
    number: str
    kind: PaymentKind
    amount_cents: int
    method: PaymentMethod
    paid_on: date
    voided: bool


@dataclass(frozen=True)
class EventAccount:
    """CA-14.5: total, pagado, saldo, fecha límite y pagos del contrato del evento (RN15)."""

    contract_id: UUID
    contract_code: str
    contract_status: ContractStatus
    total_cents: int
    paid_cents: int
    refunded_cents: int
    balance_cents: int
    balance_due_date: date
    overdue: bool
    payments: list[AccountPaymentInfo]


class GetEventAccount:
    def __init__(
        self,
        events: EventRepository,
        contracts: ContractRepository,
        entries: PaymentEntriesLookup,
        clock: Clock,
    ) -> None:
        self._events = events
        self._contracts = contracts
        self._entries = entries
        self._clock = clock

    async def __call__(self, event_id: UUID) -> EventAccount | None:
        event = await self._events.get(event_id)
        if event is None:
            return None
        contract = await self._contracts.get(event.contract_id)
        if contract is None:  # la base lo impide con una FK; solo por si acaso
            return None
        account = await account_of(contract, self._entries, self._clock)
        balance = account.balance
        return EventAccount(
            contract_id=contract.id,
            contract_code=contract.code,
            contract_status=contract.status,
            total_cents=balance.total_cents,
            paid_cents=balance.paid_cents,
            refunded_cents=balance.refunded_cents,
            balance_cents=balance.balance_cents,
            balance_due_date=balance.due_date,
            overdue=account.overdue,
            payments=[
                AccountPaymentInfo(
                    id=e.payment.id,
                    number=e.payment.number,
                    kind=e.payment.kind,
                    amount_cents=e.payment.amount_cents,
                    method=e.payment.method,
                    paid_on=e.payment.paid_on,
                    voided=e.is_voided,
                )
                for e in account.entries
            ],
        )
