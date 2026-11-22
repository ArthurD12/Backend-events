"""Casos de uso: crear una cotización en borrador y modificarla mientras siga en borrador.

HU07 (CA-07.1 a CA-07.6) y HU08 (CA-08.1). El cliente debe estar activo; el código lo genera
el sistema; los totales los calcula el dominio, nunca se toman del frontend.
"""

from dataclasses import dataclass, field
from datetime import date, time
from uuid import UUID

from local_eventos.modules.catalog.public_api import ServiceLookup
from local_eventos.modules.commercial.application.clients.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.commercial.application.quotes.errors import (
    QuoteClientInactiveError,
    QuoteClientNotFoundError,
    QuoteNotFoundError,
)
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteRepository,
)
from local_eventos.modules.commercial.application.quotes.use_cases.lines import (
    LineInput,
    build_lines,
)
from local_eventos.modules.commercial.domain.quotes.quote import (
    EventDetails,
    EventType,
    Quote,
    format_code,
)


@dataclass(frozen=True)
class QuoteCommand:
    client_id: UUID
    event_type: EventType
    event_date: date
    start_time: time
    end_time: time
    venue: str
    guests: int
    lines: list[LineInput] = field(default_factory=list)
    valid_until: date | None = None  # None: 15 días al crear; se mantiene al modificar
    notes: str | None = None

    @property
    def details(self) -> EventDetails:
        return EventDetails(
            event_type=self.event_type,
            event_date=self.event_date,
            start_time=self.start_time,
            end_time=self.end_time,
            venue=self.venue,
            guests=self.guests,
        )


class CreateQuote:
    def __init__(
        self,
        quotes: QuoteRepository,
        clients: ClientRepository,
        services: ServiceLookup,
        clock: Clock,
    ) -> None:
        self._quotes = quotes
        self._clients = clients
        self._services = services
        self._clock = clock

    async def __call__(self, command: QuoteCommand, *, created_by: UUID) -> Quote:
        today = self._clock.today()
        details = command.details.checked(today)
        await _require_active_client(self._clients, command.client_id)
        lines = await build_lines(command.lines, guests=details.guests, services=self._services)
        number = await self._quotes.next_number(today.year)
        quote = Quote.create(
            code=format_code(today.year, number),
            client_id=command.client_id,
            details=details,
            lines=lines,
            created_by=created_by,
            now=self._clock.now(),
            today=today,
            valid_until=command.valid_until,
            notes=command.notes,
        )
        await self._quotes.add(quote)
        return quote


class UpdateQuote:
    def __init__(
        self,
        quotes: QuoteRepository,
        clients: ClientRepository,
        services: ServiceLookup,
        clock: Clock,
    ) -> None:
        self._quotes = quotes
        self._clients = clients
        self._services = services
        self._clock = clock

    async def __call__(self, quote_id: UUID, command: QuoteCommand) -> Quote:
        today = self._clock.today()
        quote = await self._quotes.get(quote_id)
        if quote is None:
            raise QuoteNotFoundError()
        quote.ensure_editable(today)
        if command.client_id != quote.client_id:
            await _require_active_client(self._clients, command.client_id)
        lines = await build_lines(
            command.lines, guests=command.guests, services=self._services, previous=quote.lines
        )
        quote.update(
            details=command.details,
            lines=lines,
            valid_until=command.valid_until or quote.valid_until,
            today=today,
            notes=command.notes,
        )
        quote.client_id = command.client_id
        await self._quotes.update(quote)
        return quote


async def _require_active_client(clients: ClientRepository, client_id: UUID) -> None:
    client = await clients.get(client_id)
    if client is None:
        raise QuoteClientNotFoundError()
    if not client.active:
        raise QuoteClientInactiveError()
