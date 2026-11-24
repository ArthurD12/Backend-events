"""Historial comercial del cliente (HU05) con piezas en memoria."""

from datetime import date
from uuid import UUID, uuid4

import pytest

from local_eventos.modules.commercial.application.clients.errors import ClientNotFoundError
from local_eventos.modules.commercial.application.clients.use_cases.client_history import (
    ClientHistory,
)
from local_eventos.modules.commercial.application.contracts.use_cases.contracts import (
    AdvancePayment,
    CancelContract,
    GenerateContract,
    SignContract,
)
from local_eventos.modules.commercial.application.events.use_cases.events import (
    ConvertContractToEvent,
)
from local_eventos.modules.commercial.application.quotes.use_cases.query_quotes import (
    ChangeQuoteStatus,
)
from local_eventos.modules.commercial.domain.events.event import EventStatus
from local_eventos.modules.commercial.domain.quotes.quote import Quote, QuoteStatus
from local_eventos.modules.identity.public_api import Coordinator
from local_eventos.modules.ledger.application.use_cases.payments import RecordPayment
from local_eventos.modules.ledger.domain.payment import PaymentMethod
from tests.unit.commercial.contracts.fakes import InMemoryContractRepository
from tests.unit.commercial.events.fakes import FakeCoordinators, InMemoryEventRepository
from tests.unit.commercial.quotes.world import World, build_world, make_client
from tests.unit.ledger.fakes import InMemoryPaymentRepository

MANAGER = Coordinator(id=uuid4(), name="Rosa Huamán")


class Setup:
    def __init__(self, world: World) -> None:
        names = {world.client.id: world.client.name}
        self.world = world
        self.contracts = InMemoryContractRepository(names)
        self.events = InMemoryEventRepository(names)
        self.payments = InMemoryPaymentRepository()

    def history(self) -> ClientHistory:
        w = self.world
        return ClientHistory(w.clients, w.quotes, self.contracts, self.events, w.clock)

    async def quote(self, day: date, status: QuoteStatus | None = None, **changes: object) -> Quote:
        w = self.world
        quote = await w.create()(w.command(event_date=day, **changes), created_by=uuid4())
        if status is not None:
            await ChangeQuoteStatus(w.quotes, w.clock)(quote.id, status)
        return quote

    async def signed_contract(self, quote: Quote) -> UUID:
        w = self.world
        contract = await GenerateContract(self.contracts, w.quotes, w.clock)(
            quote.id, created_by=uuid4()
        )
        await SignContract(self.contracts, RecordPayment(self.payments), w.clock)(
            contract.id,
            signed_on=w.clock.today(),
            signer_name="José",
            advance=AdvancePayment(paid_on=w.clock.today(), method=PaymentMethod.CASH),
            recorded_by=uuid4(),
        )
        return contract.id


@pytest.fixture
async def setup() -> Setup:
    return Setup(await build_world())


async def test_ca05_historial_con_cotizaciones_eventos_y_resumen(setup: Setup) -> None:
    world = setup.world
    draft = await setup.quote(date(2026, 12, 19))
    with_event = await setup.quote(date(2027, 1, 10), QuoteStatus.ACCEPTED)
    cancelled = await setup.quote(date(2026, 12, 5), QuoteStatus.ACCEPTED)
    expired = await setup.quote(date(2027, 2, 1), QuoteStatus.SENT)
    other_client = await make_client(world.clients)
    await setup.quote(date(2026, 12, 20), client_id=other_client.id)  # no se mezcla

    contract_id = await setup.signed_contract(with_event)
    event = await ConvertContractToEvent(
        setup.events, setup.contracts, world.quotes, FakeCoordinators(MANAGER), world.clock
    )(contract_id, created_by=MANAGER.id)
    cancelled_contract = await setup.signed_contract(cancelled)
    await CancelContract(setup.contracts, RecordPayment(setup.payments), world.clock, setup.events)(
        cancelled_contract, reason="Canceló", cancelled_by=uuid4()
    )
    world.clock.advance(days=20)  # la enviada supera su vigencia de 15 días

    history = await setup.history()(world.client.id)

    assert history.client.id == world.client.id
    assert [q.id for q in history.quotes] == [expired.id, with_event.id, draft.id, cancelled.id]
    assert {q.id: q.status for q in history.quotes}[expired.id] is QuoteStatus.EXPIRED
    (item,) = history.events
    assert (item.id, item.code, item.status) == (event.id, event.code, EventStatus.SCHEDULED)
    assert item.total_cents == with_event.total_cents  # el total del contrato
    summary = history.summary
    assert (summary.quotes, summary.accepted_quotes, summary.events) == (4, 2, 1)
    assert summary.contracted_cents == with_event.total_cents  # sin el contrato anulado


async def test_ca05_cliente_sin_historial_y_desactivado(setup: Setup) -> None:
    inactive = await make_client(setup.world.clients, active=False)

    history = await setup.history()(inactive.id)

    assert (history.quotes, history.events) == ([], [])
    assert history.summary.contracted_cents == 0
    assert history.client.active is False


async def test_cliente_inexistente(setup: Setup) -> None:
    with pytest.raises(ClientNotFoundError):
        await setup.history()(uuid4())
