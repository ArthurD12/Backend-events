"""Casos de uso de contratos con piezas en memoria (HU41–HU42)."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

import pytest

from local_eventos.modules.commercial.application.contracts.errors import (
    ContractAlreadyExistsError,
    ContractNotFoundError,
    ContractQuoteNotFoundError,
)
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractFilters,
)
from local_eventos.modules.commercial.application.contracts.use_cases.contracts import (
    AdvancePayment,
    CancelContract,
    GenerateContract,
    SearchContracts,
    SignContract,
)
from local_eventos.modules.commercial.application.quotes.use_cases.query_quotes import (
    ChangeQuoteStatus,
)
from local_eventos.modules.commercial.domain.contracts.contract import (
    ContractRuleError,
    ContractStatus,
    ContractValidationError,
)
from local_eventos.modules.commercial.domain.quotes.quote import Quote, QuoteStatus
from local_eventos.modules.ledger.application.use_cases.payments import RecordPayment
from local_eventos.modules.ledger.domain.payment import (
    LedgerValidationError,
    PaymentKind,
    PaymentMethod,
)
from tests.unit.commercial.events.fakes import InMemoryEventRepository
from tests.unit.commercial.quotes.world import World, build_world
from tests.unit.ledger.fakes import InMemoryPaymentRepository

from .fakes import InMemoryContractRepository


@dataclass
class Setup:
    world: World
    contracts: InMemoryContractRepository
    payments: InMemoryPaymentRepository

    def generate(self) -> GenerateContract:
        return GenerateContract(self.contracts, self.world.quotes, self.world.clock)

    def sign(self) -> SignContract:
        return SignContract(self.contracts, RecordPayment(self.payments), self.world.clock)

    def cancel(self) -> CancelContract:
        return CancelContract(
            self.contracts, RecordPayment(self.payments), self.world.clock,
            InMemoryEventRepository(),
        )  # fmt: skip

    async def accepted_quote(self) -> Quote:
        quote = await self.world.create()(self.world.command(), created_by=uuid4())
        await ChangeQuoteStatus(self.world.quotes, self.world.clock)(quote.id, QuoteStatus.ACCEPTED)
        return quote

    def advance(self, **changes: object) -> AdvancePayment:
        data: dict[str, object] = {
            "paid_on": self.world.clock.today(),
            "method": PaymentMethod.TRANSFER,
            "reference": "Op. 778899",
            **changes,
        }
        return AdvancePayment(**data)  # type: ignore[arg-type]


@pytest.fixture
async def setup() -> Setup:
    world = await build_world()
    return Setup(
        world, InMemoryContractRepository({world.client.id: world.client.name}),
        InMemoryPaymentRepository(),
    )  # fmt: skip


async def test_ca41_genera_contrato_pendiente_con_codigo(setup: Setup) -> None:
    quote = await setup.accepted_quote()

    contract = await setup.generate()(quote.id, created_by=uuid4())

    assert contract.code == "CON-2026-0001"
    assert contract.status is ContractStatus.PENDING_SIGNATURE
    assert contract.total_cents == quote.total_cents
    assert contract.advance_cents == quote.total_cents // 2
    assert contract.id in setup.contracts.contracts


async def test_ca41_1_sin_contrato_previo_ni_cotizacion_no_aceptada(setup: Setup) -> None:
    quote = await setup.accepted_quote()
    draft = await setup.world.create()(setup.world.command(), created_by=uuid4())
    await setup.generate()(quote.id, created_by=uuid4())

    with pytest.raises(ContractAlreadyExistsError):
        await setup.generate()(quote.id, created_by=uuid4())
    with pytest.raises(ContractRuleError) as error:
        await setup.generate()(draft.id, created_by=uuid4())
    assert error.value.code == "contract.quote_not_accepted"
    with pytest.raises(ContractQuoteNotFoundError):
        await setup.generate()(uuid4(), created_by=uuid4())
    assert setup.contracts.counters == {2026: 1}  # los intentos fallidos no gastan códigos


async def test_ca42_firma_registra_el_adelanto_como_primer_pago(setup: Setup) -> None:
    quote = await setup.accepted_quote()
    contract = await setup.generate()(quote.id, created_by=uuid4(), advance_cents=200_000)
    user = uuid4()

    signed = await setup.sign()(
        contract.id,
        signed_on=setup.world.clock.today(),
        signer_name="José Ramírez",
        advance=setup.advance(),
        recorded_by=user,
    )

    [payment] = setup.payments.payments
    assert signed.status is ContractStatus.SIGNED
    assert signed.can_become_event is True
    assert signed.signature is not None and signed.signature.advance_payment_id == payment.id
    assert (payment.kind, payment.amount_cents, payment.method) == (
        PaymentKind.ADVANCE,
        200_000,
        PaymentMethod.TRANSFER,
    )
    assert payment.recorded_by == user


async def test_firma_invalida_no_registra_pago(setup: Setup) -> None:
    quote = await setup.accepted_quote()
    contract = await setup.generate()(quote.id, created_by=uuid4())
    sign = setup.sign()

    with pytest.raises(ContractValidationError):
        await sign(
            contract.id, signed_on=setup.world.clock.today(), signer_name=" ",
            advance=setup.advance(), recorded_by=uuid4(),
        )  # fmt: skip
    with pytest.raises(LedgerValidationError):
        await sign(
            contract.id, signed_on=setup.world.clock.today(), signer_name="José",
            advance=setup.advance(paid_on=setup.world.clock.today() + timedelta(days=1)),
            recorded_by=uuid4(),
        )  # fmt: skip

    assert setup.payments.payments == []
    assert setup.contracts.contracts[contract.id].status is ContractStatus.PENDING_SIGNATURE


async def test_ca42_2_firmado_no_se_vuelve_a_firmar(setup: Setup) -> None:
    quote = await setup.accepted_quote()
    contract = await setup.generate()(quote.id, created_by=uuid4())
    args = {
        "signed_on": setup.world.clock.today(),
        "signer_name": "José",
        "advance": setup.advance(),
        "recorded_by": uuid4(),
    }
    await setup.sign()(contract.id, **args)  # type: ignore[arg-type]

    with pytest.raises(ContractRuleError) as error:
        await setup.sign()(contract.id, **args)  # type: ignore[arg-type]
    assert error.value.code == "contract.not_pending"
    assert len(setup.payments.payments) == 1


async def test_r_con_3_anular_firmado_registra_la_devolucion(setup: Setup) -> None:
    quote = await setup.accepted_quote()
    contract = await setup.generate()(quote.id, created_by=uuid4())
    await setup.sign()(
        contract.id, signed_on=setup.world.clock.today(), signer_name="José",
        advance=setup.advance(), recorded_by=uuid4(),
    )  # fmt: skip

    cancelled = await setup.cancel()(
        contract.id,
        reason="El cliente canceló",
        cancelled_by=uuid4(),
        refund_cents=50_000,
        refund=setup.advance(method=PaymentMethod.CASH, reference=None),
        note="Se devolvió en efectivo",
    )

    advance, refund = setup.payments.payments
    assert cancelled.status is ContractStatus.CANCELLED
    assert (refund.kind, refund.amount_cents) == (PaymentKind.REFUND, 50_000)
    assert cancelled.cancellation is not None
    assert cancelled.cancellation.refund_payment_id == refund.id
    assert advance.kind is PaymentKind.ADVANCE


async def test_ca42_4_anular_pendiente_sin_devolucion(setup: Setup) -> None:
    quote = await setup.accepted_quote()
    contract = await setup.generate()(quote.id, created_by=uuid4())

    with pytest.raises(ContractValidationError):
        await setup.cancel()(contract.id, reason="", cancelled_by=uuid4())
    with pytest.raises(ContractValidationError):  # pendiente: no hay nada pagado que devolver
        await setup.cancel()(contract.id, reason="Motivo", cancelled_by=uuid4(), refund_cents=1)
    cancelled = await setup.cancel()(
        contract.id, reason="Cambió de proveedor", cancelled_by=uuid4()
    )

    assert cancelled.status is ContractStatus.CANCELLED
    assert setup.payments.payments == []


async def test_busca_por_codigo_cliente_y_estado(setup: Setup) -> None:
    for _ in range(2):
        quote = await setup.accepted_quote()
        await setup.generate()(quote.id, created_by=uuid4())
    search = SearchContracts(setup.contracts)

    by_client = await search(ContractFilters(text="quispe"))
    by_code = await search(ContractFilters(text=" con-2026-0002 "))
    signed = await search(ContractFilters(status=ContractStatus.SIGNED))

    assert by_client.total == 2
    assert [c.code for c in by_code.items] == ["CON-2026-0002"]
    assert signed.total == 0


async def test_contrato_inexistente(setup: Setup) -> None:
    with pytest.raises(ContractNotFoundError):
        await setup.cancel()(uuid4(), reason="x", cancelled_by=uuid4())
