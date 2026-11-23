"""Preparación compartida de las pruebas de cotizaciones: cliente, catálogo, reloj y datos."""

from dataclasses import dataclass
from datetime import date, time
from uuid import UUID

from local_eventos.modules.commercial.application.quotes.use_cases.lines import LineInput
from local_eventos.modules.commercial.application.quotes.use_cases.save_quote import (
    CreateQuote,
    QuoteCommand,
    UpdateQuote,
)
from local_eventos.modules.commercial.domain.clients.client import Client, DocumentType
from local_eventos.modules.commercial.domain.quotes.quote import EventType, LineKind
from tests.unit.commercial.clients.fakes import InMemoryClientRepository

from .fakes import FakeClock, FakeServiceLookup, InMemoryQuoteRepository


@dataclass
class World:
    quotes: InMemoryQuoteRepository
    clients: InMemoryClientRepository
    catalog: FakeServiceLookup
    clock: FakeClock
    client: Client
    buffet: UUID
    chairs: UUID

    def create(self) -> CreateQuote:
        return CreateQuote(self.quotes, self.clients, self.catalog, self.clock)

    def update(self) -> UpdateQuote:
        return UpdateQuote(self.quotes, self.clients, self.catalog, self.clock)

    def command(self, **changes: object) -> QuoteCommand:
        data: dict[str, object] = {
            "client_id": self.client.id,
            "event_type": EventType.WEDDING,
            "event_date": date(2026, 12, 19),
            "start_time": time(20, 0),
            "end_time": time(3, 0),
            "venue": "Local Los Jardines",
            "guests": 100,
            "lines": [
                LineInput(kind=LineKind.SERVICE, service_id=self.buffet),
                LineInput(kind=LineKind.SERVICE, service_id=self.chairs, quantity=100),
                LineInput(kind=LineKind.EXTRA, description="Movilidad", unit_price_cents=15000),
            ],
            **changes,
        }
        return QuoteCommand(**data)  # type: ignore[arg-type]


async def make_client(clients: InMemoryClientRepository, *, active: bool = True) -> Client:
    client = Client.register(
        name="Familia Quispe",
        document_type=DocumentType.DNI,
        document_number=str(40_000_000 + len(clients.clients)),
        phone="987654321",
    )
    if not active:
        client.deactivate()
    await clients.add(client)
    return client


async def build_world() -> World:
    clients = InMemoryClientRepository()
    client = await make_client(clients)
    catalog = FakeServiceLookup()
    buffet = catalog.add("Buffet criollo", "PER_PERSON", 4500)
    chairs = catalog.add("Silla Tiffany", "PER_UNIT", 650)
    quotes = InMemoryQuoteRepository({client.id: client.name})
    return World(quotes, clients, catalog, FakeClock(), client, buffet, chairs)
