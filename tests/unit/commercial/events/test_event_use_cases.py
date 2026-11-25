"""Convertir un contrato en evento con piezas en memoria (HU10)."""

from dataclasses import dataclass
from datetime import date, time
from uuid import UUID, uuid4

import pytest

from local_eventos.modules.commercial.application.contracts.errors import ContractNotFoundError
from local_eventos.modules.commercial.application.contracts.use_cases.contracts import (
    AdvancePayment,
    CancelContract,
    GenerateContract,
    SignContract,
)
from local_eventos.modules.commercial.application.events.errors import (
    EventAlreadyExistsError,
    EventCoordinatorInvalidError,
    EventNotFoundError,
    EventRangeInvalidError,
)
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventFilters,
)
from local_eventos.modules.commercial.application.events.use_cases.events import (
    CancelEvent,
    ConvertContractToEvent,
    EventCalendar,
    EventInfo,
    GetEvent,
    LookupEvent,
    SearchEvents,
)
from local_eventos.modules.commercial.application.quotes.use_cases.query_quotes import (
    ChangeQuoteStatus,
)
from local_eventos.modules.commercial.domain.contracts.contract import (
    Contract,
    ContractRuleError,
    ContractStatus,
    ContractValidationError,
)
from local_eventos.modules.commercial.domain.events.event import (
    EventRuleError,
    EventStatus,
    EventValidationError,
)
from local_eventos.modules.commercial.domain.quotes.quote import EventType, QuoteStatus
from local_eventos.modules.identity.public_api import Coordinator
from local_eventos.modules.ledger.application.use_cases.payments import RecordPayment
from local_eventos.modules.ledger.domain.payment import (
    LedgerValidationError,
    PaymentKind,
    PaymentMethod,
)
from tests.unit.commercial.contracts.fakes import InMemoryContractRepository
from tests.unit.commercial.quotes.world import World, build_world
from tests.unit.ledger.fakes import InMemoryPaymentRepository

from .fakes import FakeCoordinators, FakeReleaser, InMemoryEventRepository

MANAGER = Coordinator(id=uuid4(), name="Rosa Huamán")
ADMIN = Coordinator(id=uuid4(), name="Harold Canaza")


@dataclass
class Setup:
    world: World
    contracts: InMemoryContractRepository
    events: InMemoryEventRepository
    payments: InMemoryPaymentRepository
    coordinators: FakeCoordinators
    releaser: FakeReleaser

    def convert(self) -> ConvertContractToEvent:
        return ConvertContractToEvent(
            self.events, self.contracts, self.world.quotes, self.coordinators, self.world.clock
        )

    def cancel(self) -> CancelContract:
        return CancelContract(
            self.contracts, RecordPayment(self.payments), self.world.clock, self.events
        )

    def cancel_event(self) -> CancelEvent:
        return CancelEvent(
            self.events, self.contracts, RecordPayment(self.payments), self.world.clock,
            self.releaser,
        )  # fmt: skip

    async def contract(
        self, *, signed: bool = True, changes: dict[str, object] | None = None
    ) -> Contract:
        world = self.world
        quote = await world.create()(world.command(**(changes or {})), created_by=uuid4())
        await ChangeQuoteStatus(world.quotes, world.clock)(quote.id, QuoteStatus.ACCEPTED)
        contract = await GenerateContract(self.contracts, world.quotes, world.clock)(
            quote.id, created_by=uuid4()
        )
        if not signed:
            return contract
        return await SignContract(self.contracts, RecordPayment(self.payments), world.clock)(
            contract.id,
            signed_on=world.clock.today(),
            signer_name="José Ramírez",
            advance=AdvancePayment(paid_on=world.clock.today(), method=PaymentMethod.CASH),
            recorded_by=uuid4(),
        )


@pytest.fixture
async def setup() -> Setup:
    world = await build_world()
    names = {world.client.id: world.client.name}
    return Setup(
        world, InMemoryContractRepository(names), InMemoryEventRepository(names),
        InMemoryPaymentRepository(), FakeCoordinators(MANAGER, ADMIN), FakeReleaser(),
    )  # fmt: skip


async def test_ca10_convierte_contrato_firmado_con_quien_convierte_como_responsable(
    setup: Setup,
) -> None:
    contract = await setup.contract()

    event = await setup.convert()(contract.id, created_by=MANAGER.id)

    assert event.code == "EVT-2026-0001"
    assert event.status is EventStatus.SCHEDULED
    assert event.contract_id == contract.id
    assert event.coordinator_id == MANAGER.id
    assert event.event_date == date(2026, 12, 19)
    assert len(event.services) == 3
    assert await GetEvent(setup.events)(event.id) == event


async def test_ca10_6_otro_responsable_valido(setup: Setup) -> None:
    contract = await setup.contract()

    event = await setup.convert()(contract.id, created_by=MANAGER.id, coordinator_id=ADMIN.id)

    assert event.coordinator_id == ADMIN.id


@pytest.mark.parametrize("coordinator", [uuid4(), None])
async def test_ca10_6_responsable_invalido_no_gasta_codigo(
    setup: Setup, coordinator: UUID | None
) -> None:
    contract = await setup.contract()

    with pytest.raises(EventCoordinatorInvalidError):  # sin responsable: quien convierte, y no es
        await setup.convert()(contract.id, created_by=uuid4(), coordinator_id=coordinator)
    assert setup.events.counters == {}


async def test_ca10_1_contrato_pendiente_o_inexistente(setup: Setup) -> None:
    pending = await setup.contract(signed=False)

    with pytest.raises(EventRuleError) as error:
        await setup.convert()(pending.id, created_by=MANAGER.id)
    assert error.value.code == "event.contract_not_ready"
    with pytest.raises(ContractNotFoundError):
        await setup.convert()(uuid4(), created_by=MANAGER.id)
    assert setup.events.counters == {}


async def test_ca10_5_no_se_convierte_dos_veces(setup: Setup) -> None:
    contract = await setup.contract()
    await setup.convert()(contract.id, created_by=MANAGER.id)

    with pytest.raises(EventAlreadyExistsError):
        await setup.convert()(contract.id, created_by=MANAGER.id)
    assert setup.events.counters == {2026: 1}


async def test_r_evt_3_contrato_con_evento_no_se_anula(setup: Setup) -> None:
    contract = await setup.contract()
    await setup.convert()(contract.id, created_by=MANAGER.id)

    with pytest.raises(ContractRuleError) as error:
        await setup.cancel()(contract.id, reason="Canceló", cancelled_by=uuid4(), refund_cents=1)

    assert error.value.code == "contract.has_event"
    stored = await setup.contracts.get(contract.id)
    assert stored is not None and stored.status is ContractStatus.SIGNED
    assert len(setup.payments.payments) == 1  # solo el adelanto: no se registró la devolución


async def test_busca_por_texto_estado_y_fechas(setup: Setup) -> None:
    for _ in range(2):
        await setup.convert()((await setup.contract()).id, created_by=MANAGER.id)
    search = SearchEvents(setup.events)

    by_client = await search(EventFilters(text="quispe"))
    by_code = await search(EventFilters(text=" evt-2026-0002 "))
    december = await search(EventFilters(date_from=date(2026, 12, 1), date_to=date(2026, 12, 31)))
    cancelled = await search(EventFilters(status=EventStatus.CANCELLED))

    assert by_client.total == 2
    assert [e.code for e in by_code.items] == ["EVT-2026-0002"]
    assert december.total == 2
    assert cancelled.total == 0
    with pytest.raises(EventNotFoundError):
        await GetEvent(setup.events)(uuid4())


async def test_ca11_c4_cancelar_evento_anula_contrato_y_registra_devolucion(setup: Setup) -> None:
    contract = await setup.contract()
    event = await setup.convert()(contract.id, created_by=MANAGER.id)
    today = setup.world.clock.today()

    cancelled = await setup.cancel_event()(
        event.id,
        reason=" El cliente   canceló ",
        cancelled_by=MANAGER.id,
        refund_cents=50_000,
        refund=AdvancePayment(paid_on=today, method=PaymentMethod.TRANSFER, reference="Op. 9"),
        note="Acordado por teléfono",
    )

    stored = await setup.contracts.get(contract.id)
    advance, refund = setup.payments.payments
    assert cancelled.status is EventStatus.CANCELLED
    assert cancelled.cancellation is not None
    assert cancelled.cancellation.reason == "El cliente canceló"
    assert await GetEvent(setup.events)(event.id) == cancelled
    assert stored is not None and stored.status is ContractStatus.CANCELLED
    assert stored.cancellation is not None
    assert (stored.cancellation.reason, stored.cancellation.refund_cents) == (
        "El cliente canceló",
        50_000,
    )
    assert stored.cancellation.refund_payment_id == refund.id
    assert (advance.kind, refund.kind) == (PaymentKind.ADVANCE, PaymentKind.REFUND)
    # R-STF-5: en el mismo paso se libera al personal del evento.
    assert setup.releaser.released == [(event.id, MANAGER.id, setup.world.clock.now())]


async def test_ca11_c4_sin_devolucion(setup: Setup) -> None:
    event = await setup.convert()((await setup.contract()).id, created_by=MANAGER.id)

    await setup.cancel_event()(event.id, reason="Cambió de proveedor", cancelled_by=MANAGER.id)

    assert len(setup.payments.payments) == 1  # solo el adelanto


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"reason": " "}, EventValidationError),
        ({"reason": "Canceló", "refund_cents": 999_999_999}, ContractValidationError),
        (
            {
                "reason": "Canceló",
                "refund_cents": 1_000,
                "refund": AdvancePayment(paid_on=date(2030, 1, 1), method=PaymentMethod.CASH),
            },
            LedgerValidationError,
        ),
    ],
)
async def test_ca11_c4_si_algo_falla_no_cambia_nada(
    setup: Setup, changes: dict[str, object], error: type[Exception]
) -> None:
    contract = await setup.contract()
    event = await setup.convert()(contract.id, created_by=MANAGER.id)

    with pytest.raises(error):
        await setup.cancel_event()(event.id, cancelled_by=MANAGER.id, **changes)  # type: ignore[arg-type]

    stored_event = await setup.events.get(event.id)
    stored_contract = await setup.contracts.get(contract.id)
    assert stored_event is not None and stored_event.status is EventStatus.SCHEDULED
    assert stored_contract is not None and stored_contract.status is ContractStatus.SIGNED
    assert len(setup.payments.payments) == 1
    assert setup.releaser.released == []


async def test_ca11_c1_no_se_cancela_dos_veces_ni_uno_inexistente(setup: Setup) -> None:
    event = await setup.convert()((await setup.contract()).id, created_by=MANAGER.id)
    await setup.cancel_event()(event.id, reason="Canceló", cancelled_by=MANAGER.id)

    with pytest.raises(EventRuleError) as error:
        await setup.cancel_event()(event.id, reason="Otra vez", cancelled_by=MANAGER.id)
    assert error.value.code == "event.not_cancellable"
    with pytest.raises(EventNotFoundError):
        await setup.cancel_event()(uuid4(), reason="x", cancelled_by=MANAGER.id)


async def test_event_lookup_para_otros_modulos(setup: Setup) -> None:
    event = await setup.convert()((await setup.contract()).id, created_by=MANAGER.id)
    lookup = LookupEvent(setup.events)

    assert await lookup(event.id) == EventInfo(
        id=event.id,
        code="EVT-2026-0001",
        status=EventStatus.SCHEDULED,
        event_date=date(2026, 12, 19),
        start_time=time(20),
        end_time=time(3),
    )
    assert await lookup(uuid4()) is None


async def _event_on(setup: Setup, day: date, **changes: object) -> UUID:
    contract = await setup.contract(changes={"event_date": day, **changes})
    return (await setup.convert()(contract.id, created_by=MANAGER.id)).id


async def test_ca12_calendario_del_periodo_ordenado_por_fecha_y_hora(setup: Setup) -> None:
    late = await _event_on(setup, date(2026, 12, 19), start_time=time(20), end_time=time(3))
    early = await _event_on(setup, date(2026, 12, 19), start_time=time(12), end_time=time(16))
    first = await _event_on(setup, date(2026, 12, 1))
    await _event_on(setup, date(2027, 1, 5))  # fuera del periodo

    december = await EventCalendar(setup.events)(date(2026, 12, 1), date(2026, 12, 31))

    assert [e.id for e in december] == [first, early, late]


async def test_ca12_3_filtra_por_estado_tipo_y_cliente(setup: Setup) -> None:
    wedding = await _event_on(setup, date(2026, 12, 19))
    birthday = await _event_on(setup, date(2026, 12, 20), event_type=EventType.BIRTHDAY)
    await setup.cancel_event()(wedding, reason="Canceló", cancelled_by=MANAGER.id)
    calendar = EventCalendar(setup.events)
    december = (date(2026, 12, 1), date(2026, 12, 31))

    by_type = await calendar(*december, EventFilters(event_type=EventType.BIRTHDAY))
    cancelled = await calendar(*december, EventFilters(status=EventStatus.CANCELLED))
    by_client = await calendar(*december, EventFilters(text=" QUISPE "))
    nobody = await calendar(*december, EventFilters(text="ramírez"))

    assert [e.id for e in by_type] == [birthday]
    assert [e.id for e in cancelled] == [wedding]
    assert len(by_client) == 2  # R-CAL-2: los cancelados también aparecen
    assert nobody == []


@pytest.mark.parametrize(
    ("start", "end"),
    [(date(2026, 12, 31), date(2026, 12, 1)), (date(2026, 1, 1), date(2026, 4, 3))],
)
async def test_ca12_rango_invalido_o_mayor_a_92_dias(setup: Setup, start: date, end: date) -> None:
    with pytest.raises(EventRangeInvalidError):
        await EventCalendar(setup.events)(start, end)


async def test_ca12_rango_de_92_dias_es_valido(setup: Setup) -> None:
    assert await EventCalendar(setup.events)(date(2026, 1, 1), date(2026, 4, 2)) == []
