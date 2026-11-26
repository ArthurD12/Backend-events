"""Casos de uso de eventos: convertir un contrato firmado en evento (HU10), consultarlos y
cancelarlos (HU11, parte)."""

from dataclasses import dataclass, replace
from datetime import date
from uuid import UUID

from local_eventos.modules.commercial.application.contracts.errors import ContractNotFoundError
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractRepository,
)
from local_eventos.modules.commercial.application.contracts.use_cases.contracts import (
    AdvancePayment,
)
from local_eventos.modules.commercial.application.events.errors import (
    EventAlreadyExistsError,
    EventCoordinatorInvalidError,
    EventNotFoundError,
    EventRangeInvalidError,
)
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventFilters,
    EventRepository,
    EventSummary,
)
from local_eventos.modules.commercial.application.events.ports.reservation_releaser import (
    ReservationReleaser,
)
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteRepository,
)
from local_eventos.modules.commercial.domain.events.event import Event, format_event_code
from local_eventos.modules.identity.public_api import CoordinatorLookup
from local_eventos.modules.ledger.public_api import (
    PaymentKind,
    PaymentMethod,
    PaymentRecorder,
    PaymentRequest,
)

MAX_PAGE_SIZE = 100
CALENDAR_MAX_DAYS = 92
_CALENDAR_LIMIT = 1_000  # una MYPE no llega a tantos eventos en 92 días


@dataclass(frozen=True)
class EventPage:
    items: list[EventSummary]
    total: int
    page: int
    page_size: int


class ConvertContractToEvent:
    def __init__(
        self,
        events: EventRepository,
        contracts: ContractRepository,
        quotes: QuoteRepository,
        coordinators: CoordinatorLookup,
        clock: Clock,
    ) -> None:
        self._events = events
        self._contracts = contracts
        self._quotes = quotes
        self._coordinators = coordinators
        self._clock = clock

    async def __call__(
        self, contract_id: UUID, *, created_by: UUID, coordinator_id: UUID | None = None
    ) -> Event:
        """CA-10.1 a CA-10.5. Si no se indica responsable, lo es quien convierte (R-EVT-2)."""
        contract = await self._contracts.get(contract_id)
        if contract is None:
            raise ContractNotFoundError()
        quote = await self._quotes.get(contract.quote_id)
        if quote is None:  # la base lo impide con una FK; solo por si acaso
            raise ContractNotFoundError()
        if await self._events.get_by_contract(contract_id) is not None:
            raise EventAlreadyExistsError()
        coordinator = coordinator_id or created_by
        if coordinator not in {c.id for c in await self._coordinators()}:
            raise EventCoordinatorInvalidError()
        today, now = self._clock.today(), self._clock.now()
        # Valida con un código provisional: si algo falla, no se gasta un correlativo.
        Event.from_contract(
            code="", contract=contract, quote=quote, coordinator_id=coordinator,
            created_by=created_by, now=now,
        )  # fmt: skip
        number = await self._events.next_number(today.year)
        event = Event.from_contract(
            code=format_event_code(today.year, number),
            contract=contract,
            quote=quote,
            coordinator_id=coordinator,
            created_by=created_by,
            now=now,
        )
        await self._events.add(event)
        return event


class GetEvent:
    def __init__(self, events: EventRepository) -> None:
        self._events = events

    async def __call__(self, event_id: UUID) -> Event:
        event = await self._events.get(event_id)
        if event is None:
            raise EventNotFoundError()
        return event


class SearchEvents:
    def __init__(self, events: EventRepository) -> None:
        self._events = events

    async def __call__(
        self, filters: EventFilters, *, page: int = 1, page_size: int = 20
    ) -> EventPage:
        page = max(page, 1)
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        items, total = await self._events.search(
            replace(filters, text=" ".join(filters.text.split())),
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return EventPage(items=items, total=total, page=page, page_size=page_size)


class EventCalendar:
    """HU12: todos los eventos de un periodo (mes, semana o día), sin paginar, por fecha y hora."""

    def __init__(self, events: EventRepository) -> None:
        self._events = events

    async def __call__(
        self, date_from: date, date_to: date, filters: EventFilters | None = None
    ) -> list[EventSummary]:
        if date_to < date_from or (date_to - date_from).days + 1 > CALENDAR_MAX_DAYS:
            raise EventRangeInvalidError(CALENDAR_MAX_DAYS)
        base = filters or EventFilters()
        items, _ = await self._events.search(
            replace(base, text=" ".join(base.text.split()), date_from=date_from, date_to=date_to),
            limit=_CALENDAR_LIMIT,
            offset=0,
        )
        return items


class CancelEvent:
    """Cancela el evento y anula su contrato en un solo paso (CA-11.C4, R-EVT-4).

    Si hubo devolución, se registra en pagos dentro de la misma transacción: o se guarda todo,
    o nada. Todo se valida antes de registrar el pago.
    """

    def __init__(
        self,
        events: EventRepository,
        contracts: ContractRepository,
        payments: PaymentRecorder,
        clock: Clock,
        reservations: ReservationReleaser,
    ) -> None:
        self._events = events
        self._contracts = contracts
        self._payments = payments
        self._clock = clock
        self._reservations = reservations

    async def __call__(
        self,
        event_id: UUID,
        *,
        reason: str,
        cancelled_by: UUID,
        refund_cents: int | None = None,
        refund: AdvancePayment | None = None,
        note: str | None = None,
    ) -> Event:
        today, now = self._clock.today(), self._clock.now()
        event = await GetEvent(self._events)(event_id)
        cleaned = event.check_cancellation(reason)
        contract = await self._contracts.get(event.contract_id)
        if contract is None:  # la base lo impide con una FK; solo por si acaso
            raise ContractNotFoundError()
        contract.check_cancellation(cleaned, refund_cents)
        refund_payment_id = None
        if refund_cents is not None:
            how = refund or AdvancePayment(paid_on=today, method=PaymentMethod.CASH)
            payment = await self._payments(
                PaymentRequest(
                    contract_id=contract.id,
                    kind=PaymentKind.REFUND,
                    amount_cents=refund_cents,
                    method=how.method,
                    reference=how.reference,
                    paid_on=how.paid_on,
                    recorded_by=cancelled_by,
                ),
                now=now,
                today=today,
            )
            refund_payment_id = payment.id
        change = event.cancel(reason=cleaned, cancelled_by=cancelled_by, now=now)
        # Primero el evento: la base lo exige (R-EVT-3). El cambio queda en el historial.
        await self._events.update(event, change)
        contract.cancel(
            reason=cleaned,
            refund_cents=refund_cents,
            refund_payment_id=refund_payment_id,
            note=note,
            cancelled_by=cancelled_by,
            now=now,
        )
        await self._contracts.update(contract)
        await self._reservations(event.id)  # R-REC-3: lo reservado vuelve a estar disponible
        return event
