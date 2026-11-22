"""Casos de uso de eventos (HU10): convertir un contrato firmado en evento y consultarlos."""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.commercial.application.contracts.errors import ContractNotFoundError
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractRepository,
)
from local_eventos.modules.commercial.application.events.errors import (
    EventAlreadyExistsError,
    EventCoordinatorInvalidError,
    EventNotFoundError,
)
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventFilters,
    EventRepository,
    EventSummary,
)
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteRepository,
)
from local_eventos.modules.commercial.domain.events.event import Event, format_event_code
from local_eventos.modules.identity.public_api import CoordinatorLookup

MAX_PAGE_SIZE = 100


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
            EventFilters(
                text=" ".join(filters.text.split()),
                status=filters.status,
                date_from=filters.date_from,
                date_to=filters.date_to,
            ),
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return EventPage(items=items, total=total, page=page, page_size=page_size)
