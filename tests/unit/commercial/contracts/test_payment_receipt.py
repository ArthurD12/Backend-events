"""Comprobante en PDF de un pago (HU20): número, cuenta después del pago y marca ANULADO."""

from uuid import uuid4

import pytest

from local_eventos.modules.commercial.application.contracts.ports.receipt import PaymentReceipt
from local_eventos.modules.commercial.application.contracts.use_cases.payments import (
    NewPayment,
    RecordContractPayment,
)
from local_eventos.modules.commercial.application.contracts.use_cases.receipt import (
    RenderPaymentReceipt,
)
from local_eventos.modules.commercial.application.quotes.ports.document import CompanyProfile
from local_eventos.modules.commercial.domain.contracts.contract import Contract
from local_eventos.modules.commercial.infrastructure.quote_pdf import soles
from local_eventos.modules.commercial.infrastructure.receipt_pdf import ReportLabReceiptRenderer
from local_eventos.modules.ledger.application.errors import PaymentNotFoundError
from local_eventos.modules.ledger.application.use_cases.payments import (
    ContractPaymentEntries,
    FindPayment,
    RecordPayment,
    VoidPayment,
)
from local_eventos.modules.ledger.domain.payment import PaymentMethod
from tests.unit.commercial.events.fakes import InMemoryEventRepository

from .test_contract_use_cases import Setup, setup  # noqa: F401 - fixture

COMPANY = CompanyProfile(name="Darze Catering", ruc="20123456789")


class SpyRenderer:
    def __init__(self) -> None:
        self.receipts: list[PaymentReceipt] = []

    def render(self, receipt: PaymentReceipt) -> bytes:
        self.receipts.append(receipt)
        return b"%PDF-falso"


class FakeNames:
    def __init__(self, names: dict[object, str]) -> None:
        self.names = names

    async def __call__(self, user_ids: object) -> dict[object, str]:
        return dict(self.names)


async def _signed_with_payments(setup: Setup, user: object) -> tuple[Contract, list[object]]:  # noqa: F811
    quote = await setup.accepted_quote()
    contract = await setup.generate()(quote.id, created_by=uuid4(), advance_cents=200_000)
    await setup.sign()(
        contract.id, signed_on=setup.world.clock.today(), signer_name="José",
        advance=setup.advance(), recorded_by=uuid4(),
    )  # fmt: skip
    record = RecordContractPayment(
        setup.contracts, ContractPaymentEntries(setup.payments), RecordPayment(setup.payments),
        setup.world.clock,
    )  # fmt: skip
    ids = []
    for amount in (50_000, 30_000, 20_000):
        _, entry = await record(
            contract.id,
            NewPayment(amount, setup.world.clock.today(), PaymentMethod.CASH, "Op 7"),
            recorded_by=user,  # type: ignore[arg-type]
        )
        ids.append(entry.payment.id)
    return contract, ids


def _use_case(setup: Setup, renderer: object, names: object) -> RenderPaymentReceipt:  # noqa: F811
    return RenderPaymentReceipt(
        finder=FindPayment(setup.payments),
        entries=ContractPaymentEntries(setup.payments),
        contracts=setup.contracts,
        clients=setup.world.clients,
        events=InMemoryEventRepository(),
        names=names,  # type: ignore[arg-type]
        renderer=renderer,  # type: ignore[arg-type]
        company=COMPANY,
        clock=setup.world.clock,
    )


async def test_ca20_2_saldo_despues_de_ese_pago_sin_otros_anulados(setup: Setup) -> None:  # noqa: F811
    user = uuid4()
    contract, (first, second, third) = await _signed_with_payments(setup, user)
    await VoidPayment(setup.payments)(
        second, reason="Error", voided_by=uuid4(), now=setup.world.clock.now()
    )  # type: ignore[arg-type]
    renderer = SpyRenderer()

    filename, content = await _use_case(setup, renderer, FakeNames({user: "Ana"}))(third)  # type: ignore[arg-type]

    [receipt] = renderer.receipts
    assert (filename, content) == ("PAG-2026-0004.pdf", b"%PDF-falso")
    assert receipt.paid_after_cents == 200_000 + 50_000 + 20_000  # el 2.º pago anulado no cuenta
    assert receipt.balance_after_cents == contract.total_cents - 270_000
    assert receipt.recorded_by_name == "Ana" and receipt.client.id == setup.world.client.id


async def test_ca20_3_pago_anulado_sale_con_marca_y_motivo(setup: Setup) -> None:  # noqa: F811
    user = uuid4()
    contract, (first, _, _) = await _signed_with_payments(setup, user)
    await VoidPayment(setup.payments)(
        first, reason="Voucher falso", voided_by=uuid4(), now=setup.world.clock.now()
    )  # type: ignore[arg-type]
    renderer = SpyRenderer()
    await _use_case(setup, renderer, FakeNames({user: "Ana"}))(first)  # type: ignore[arg-type]
    [receipt] = renderer.receipts

    pdf = ReportLabReceiptRenderer(compress=False).render(receipt)

    assert receipt.paid_after_cents == 250_000  # cuenta como quedó al registrarlo
    assert pdf.startswith(b"%PDF")
    for text in (
        "PAG-2026-0002",
        "ANULADO",
        "Voucher falso",
        contract.code,
        "Pago parcial",
        "Ana",
        soles(contract.total_cents),
        soles(contract.total_cents - 250_000),
        "No es boleta ni factura",
    ):
        assert text.encode() in pdf, text


async def test_pago_inexistente(setup: Setup) -> None:  # noqa: F811
    with pytest.raises(PaymentNotFoundError):
        await _use_case(setup, SpyRenderer(), FakeNames({}))(uuid4())
