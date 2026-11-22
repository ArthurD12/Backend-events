"""Casos de uso de cotizaciones con piezas en memoria (HU07, HU08)."""

from dataclasses import dataclass
from datetime import date, time, timedelta
from uuid import UUID, uuid4

import pytest

from local_eventos.modules.commercial.application.quotes.errors import (
    QuoteClientInactiveError,
    QuoteClientNotFoundError,
    QuoteNotFoundError,
    QuoteServiceInactiveError,
    QuoteServiceNotFoundError,
)
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteFilters,
)
from local_eventos.modules.commercial.application.quotes.use_cases.lines import LineInput
from local_eventos.modules.commercial.application.quotes.use_cases.query_quotes import (
    ChangeQuoteStatus,
    GetQuote,
    SearchQuotes,
)
from local_eventos.modules.commercial.application.quotes.use_cases.save_quote import (
    CreateQuote,
    QuoteCommand,
    UpdateQuote,
)
from local_eventos.modules.commercial.domain.clients.client import Client, DocumentType
from local_eventos.modules.commercial.domain.quotes.quote import (
    EventType,
    LineKind,
    QuoteRuleError,
    QuoteStatus,
    QuoteValidationError,
)
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


async def _client(clients: InMemoryClientRepository, *, active: bool = True) -> Client:
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


@pytest.fixture
async def world() -> World:
    clients = InMemoryClientRepository()
    client = await _client(clients)
    catalog = FakeServiceLookup()
    buffet = catalog.add("Buffet criollo", "PER_PERSON", 4500)
    chairs = catalog.add("Silla Tiffany", "PER_UNIT", 650)
    quotes = InMemoryQuoteRepository({client.id: client.name})
    return World(quotes, clients, catalog, FakeClock(), client, buffet, chairs)


async def test_ca07_crea_borrador_con_codigo_lineas_congeladas_y_total(world: World) -> None:
    quote = await world.create()(world.command(), created_by=uuid4())

    assert quote.code == "COT-2026-0001"
    assert quote.status is QuoteStatus.DRAFT
    buffet, chairs, transport = quote.lines
    assert (buffet.description, buffet.quantity, buffet.unit_price_cents) == (
        "Buffet criollo",
        100,
        4500,
    )
    assert buffet.catalog_price_cents == 4500
    assert (chairs.quantity, chairs.subtotal_cents) == (100, 65_000)
    assert (transport.description, transport.quantity) == ("Movilidad", 1)
    assert quote.total_cents == 450_000 + 65_000 + 15_000
    assert quote.id in world.quotes.quotes


async def test_ca07_4_codigos_correlativos_por_anio(world: World) -> None:
    first = await world.create()(world.command(), created_by=uuid4())
    second = await world.create()(world.command(), created_by=uuid4())
    world.clock.advance(days=40)
    next_year = await world.create()(world.command(event_date=date(2027, 2, 1)), created_by=uuid4())

    assert [first.code, second.code, next_year.code] == [
        "COT-2026-0001",
        "COT-2026-0002",
        "COT-2027-0001",
    ]


async def test_regla_10_el_precio_de_la_linea_se_puede_negociar(world: World) -> None:
    command = world.command(
        lines=[LineInput(kind=LineKind.SERVICE, service_id=world.buffet, unit_price_cents=4000)]
    )

    [line] = (await world.create()(command, created_by=uuid4())).lines

    assert (line.unit_price_cents, line.catalog_price_cents) == (4000, 4500)


async def test_ca07_1_el_cliente_debe_existir_y_estar_activo(world: World) -> None:
    inactive = await _client(world.clients, active=False)

    with pytest.raises(QuoteClientInactiveError):
        await world.create()(world.command(client_id=inactive.id), created_by=uuid4())
    with pytest.raises(QuoteClientNotFoundError):
        await world.create()(world.command(client_id=uuid4()), created_by=uuid4())


async def test_regla_2_solo_servicios_activos_y_existentes(world: World) -> None:
    world.catalog.change(world.chairs, active=False)

    with pytest.raises(QuoteServiceInactiveError) as error:
        await world.create()(world.command(), created_by=uuid4())
    assert "Silla Tiffany" in str(error.value)
    with pytest.raises(QuoteServiceNotFoundError):
        await world.create()(
            world.command(lines=[LineInput(kind=LineKind.SERVICE, service_id=uuid4())]),
            created_by=uuid4(),
        )


async def test_concepto_adicional_necesita_monto(world: World) -> None:
    with pytest.raises(QuoteValidationError) as error:
        await world.create()(
            world.command(lines=[LineInput(kind=LineKind.EXTRA, description="Recargo")]),
            created_by=uuid4(),
        )
    assert error.value.code == "quote.price_invalid"


async def test_regla_6_cambiar_el_catalogo_no_altera_la_cotizacion(world: World) -> None:
    quote = await world.create()(world.command(), created_by=uuid4())
    world.catalog.change(world.buffet, reference_price_cents=9900, name="Buffet premium")
    world.catalog.change(world.chairs, active=False)

    edited = await world.update()(quote.id, world.command(guests=120))

    buffet, chairs, _ = edited.lines
    assert (buffet.description, buffet.catalog_price_cents, buffet.unit_price_cents) == (
        "Buffet criollo",
        4500,
        4500,
    )
    assert chairs.description == "Silla Tiffany"  # ya estaba: no importa que se desactivara
    assert buffet.quantity == 120  # por persona = invitados


async def test_ca08_1_editar_borrador_y_agregar_servicio_nuevo(world: World) -> None:
    quote = await world.create()(world.command(), created_by=uuid4())
    drinks = world.catalog.add("Chicha morada (jarra)", "PER_UNIT", 1800)

    edited = await world.update()(
        quote.id,
        world.command(
            venue="Casa de campo en Cieneguilla",
            lines=[LineInput(kind=LineKind.SERVICE, service_id=drinks, quantity=10)],
            valid_until=date(2026, 12, 10),
        ),
    )

    assert edited.details.venue == "Casa de campo en Cieneguilla"
    assert edited.total_cents == 18_000
    assert edited.valid_until == date(2026, 12, 10)
    assert world.quotes.quotes[quote.id].total_cents == 18_000


async def test_ca08_4_no_editable_responde_eso_primero(world: World) -> None:
    quote = await world.create()(world.command(), created_by=uuid4())
    await ChangeQuoteStatus(world.quotes, world.clock)(quote.id, QuoteStatus.ACCEPTED)
    world.catalog.change(world.buffet, active=False)

    with pytest.raises(QuoteRuleError) as error:
        await world.update()(quote.id, world.command(client_id=uuid4()))
    assert error.value.code == "quote.not_editable"


async def test_ca08_2_cambia_de_estado_y_queda_guardado(world: World) -> None:
    quote = await world.create()(world.command(), created_by=uuid4())
    change = ChangeQuoteStatus(world.quotes, world.clock)

    await change(quote.id, QuoteStatus.SENT)
    await change(quote.id, QuoteStatus.ACCEPTED)

    assert (await GetQuote(world.quotes)(quote.id)).status is QuoteStatus.ACCEPTED
    with pytest.raises(QuoteNotFoundError):
        await change(uuid4(), QuoteStatus.SENT)


async def test_ca08_3_y_ca08_5_busca_por_estado_incluida_vencida(world: World) -> None:
    old = await world.create()(world.command(valid_until=date(2026, 11, 25)), created_by=uuid4())
    sent = await world.create()(world.command(), created_by=uuid4())
    await ChangeQuoteStatus(world.quotes, world.clock)(sent.id, QuoteStatus.SENT)
    world.clock.advance(days=5)
    search = SearchQuotes(world.quotes, world.clock)

    expired = await search(QuoteFilters(status=QuoteStatus.EXPIRED))
    by_code = await search(QuoteFilters(text=" cot-2026-0002 "))
    by_client = await search(QuoteFilters(text="quispe"))

    assert [s.id for s in expired.items] == [old.id]
    assert [s.code for s in by_code.items] == ["COT-2026-0002"]
    assert by_client.total == 2


async def test_ca08_5_busca_por_fecha_del_evento_y_pagina(world: World) -> None:
    for day in (5, 10, 15):
        await world.create()(world.command(event_date=date(2026, 12, day)), created_by=uuid4())
    search = SearchQuotes(world.quotes, world.clock)

    december_first_half = await search(
        QuoteFilters(event_date_from=date(2026, 12, 1), event_date_to=date(2026, 12, 12))
    )
    page_two = await search(QuoteFilters(), page=2, page_size=2)

    assert december_first_half.total == 2
    assert (len(page_two.items), page_two.total) == (1, 3)


async def test_r_cot_4_la_fecha_pasada_se_rechaza_antes_de_gastar_un_codigo(world: World) -> None:
    with pytest.raises(QuoteValidationError):
        await world.create()(
            world.command(event_date=world.clock.today() - timedelta(days=1)), created_by=uuid4()
        )
    assert world.quotes.counters == {}
