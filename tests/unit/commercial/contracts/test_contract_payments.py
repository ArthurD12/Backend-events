"""Pagos del contrato y su saldo (HU19, RN14, RN15) con piezas en memoria. Sin base de datos."""

from datetime import timedelta
from uuid import uuid4

import pytest

from local_eventos.modules.commercial.application.contracts.errors import ContractNotFoundError
from local_eventos.modules.commercial.application.contracts.use_cases.contracts import (
    CancelContract,
)
from local_eventos.modules.commercial.application.contracts.use_cases.payments import (
    GetContractAccount,
    NewPayment,
    RecordContractPayment,
    VoidContractPayment,
)
from local_eventos.modules.commercial.domain.contracts.contract import (
    Contract,
    ContractBalance,
    ContractRuleError,
    ContractValidationError,
)
from local_eventos.modules.ledger.application.errors import (
    PaymentAlreadyVoidedError,
    PaymentNotFoundError,
)
from local_eventos.modules.ledger.application.use_cases.payments import (
    ContractPaymentEntries,
    RecordPayment,
    VoidPayment,
)
from local_eventos.modules.ledger.domain.payment import (
    LedgerRuleError,
    LedgerValidationError,
    PaymentKind,
    PaymentMethod,
)
from tests.unit.commercial.events.fakes import InMemoryEventRepository

from .test_contract_use_cases import Setup, setup  # noqa: F401 - fixture


async def _signed(setup: Setup) -> Contract:  # noqa: F811
    quote = await setup.accepted_quote()
    contract = await setup.generate()(quote.id, created_by=uuid4(), advance_cents=200_000)
    return await setup.sign()(
        contract.id,
        signed_on=setup.world.clock.today(),
        signer_name="José Ramírez",
        advance=setup.advance(),
        recorded_by=uuid4(),
    )


def _record(setup: Setup) -> RecordContractPayment:  # noqa: F811
    return RecordContractPayment(
        setup.contracts,
        ContractPaymentEntries(setup.payments),
        RecordPayment(setup.payments),
        setup.world.clock,
    )


def _void(setup: Setup) -> VoidContractPayment:  # noqa: F811
    return VoidContractPayment(
        setup.contracts,
        ContractPaymentEntries(setup.payments),
        VoidPayment(setup.payments),
        setup.world.clock,
    )


def _account(setup: Setup) -> GetContractAccount:  # noqa: F811
    return GetContractAccount(
        setup.contracts, ContractPaymentEntries(setup.payments), setup.world.clock
    )


def _payment(setup: Setup, amount: int) -> NewPayment:  # noqa: F811
    return NewPayment(
        amount_cents=amount, paid_on=setup.world.clock.today(), method=PaymentMethod.CASH
    )


async def test_ca19_1_pago_parcial_en_contrato_firmado(setup: Setup) -> None:  # noqa: F811
    contract = await _signed(setup)
    user = uuid4()

    account, entry = await _record(setup)(contract.id, _payment(setup, 100_000), recorded_by=user)

    assert entry.payment.kind is PaymentKind.INSTALLMENT
    assert entry.payment.number == "PAG-2026-0002"  # el adelanto es el 0001
    assert entry.payment.recorded_by == user
    assert (account.balance.paid_cents, account.balance.balance_cents) == (
        300_000,
        contract.total_cents - 300_000,
    )
    assert [e.payment.kind for e in account.entries] == [
        PaymentKind.ADVANCE,
        PaymentKind.INSTALLMENT,
    ]


async def test_ca19_2_hasta_saldo_cero_y_el_siguiente_falla(setup: Setup) -> None:  # noqa: F811
    contract = await _signed(setup)
    record = _record(setup)

    account, _ = await record(
        contract.id, _payment(setup, contract.total_cents - 200_000), recorded_by=uuid4()
    )
    with pytest.raises(ContractValidationError) as error:
        await record(contract.id, _payment(setup, 1), recorded_by=uuid4())

    assert account.balance.balance_cents == 0
    assert error.value.code == "payment.exceeds_balance"
    assert "S/ 0.00" in str(error.value)


async def test_ca19_2_monto_invalido(setup: Setup) -> None:  # noqa: F811
    contract = await _signed(setup)
    with pytest.raises(LedgerValidationError) as error:
        await _record(setup)(contract.id, _payment(setup, 0), recorded_by=uuid4())
    assert error.value.code == "payment.amount_invalid"


async def test_ca19_6_sin_pagos_en_contrato_pendiente_o_anulado(setup: Setup) -> None:  # noqa: F811
    quote = await setup.accepted_quote()
    pending = await setup.generate()(quote.id, created_by=uuid4())
    signed = await _signed(setup)
    await CancelContract(
        setup.contracts, RecordPayment(setup.payments), setup.world.clock,
        InMemoryEventRepository(),
    )(signed.id, reason="Canceló", cancelled_by=uuid4())  # fmt: skip

    for contract_id in (pending.id, signed.id):
        with pytest.raises(ContractRuleError) as error:
            await _record(setup)(contract_id, _payment(setup, 1), recorded_by=uuid4())
        assert error.value.code == "contract.not_signed"
    with pytest.raises(ContractNotFoundError):
        await _record(setup)(uuid4(), _payment(setup, 1), recorded_by=uuid4())


async def test_ca19_3_ca19_5_anular_devuelve_el_monto_al_saldo(setup: Setup) -> None:  # noqa: F811
    contract = await _signed(setup)
    _, entry = await _record(setup)(contract.id, _payment(setup, 100_000), recorded_by=uuid4())

    account = await _void(setup)(entry.payment.id, reason="Monto errado", voided_by=uuid4())

    assert account.balance.balance_cents == contract.total_cents - 200_000
    assert [e.is_voided for e in account.entries] == [False, True]
    with pytest.raises(PaymentAlreadyVoidedError):
        await _void(setup)(entry.payment.id, reason="Otra vez", voided_by=uuid4())
    with pytest.raises(LedgerRuleError):  # el adelanto no se anula por aquí
        await _void(setup)(account.entries[0].payment.id, reason="x", voided_by=uuid4())
    with pytest.raises(PaymentNotFoundError):
        await _void(setup)(uuid4(), reason="x", voided_by=uuid4())


async def test_ca19_4_cuenta_con_fecha_limite_y_aviso_de_vencido(setup: Setup) -> None:  # noqa: F811
    contract = await _signed(setup)

    before = await _account(setup)(contract.id)
    setup.world.clock.advance(
        days=(contract.balance_due_date - before.contract.created_at.date()).days + 2
    )
    after = await _account(setup)(contract.id)

    assert (before.balance.due_date, before.overdue) == (contract.balance_due_date, False)
    assert after.overdue is True  # R-PAG-2: solo avisa
    with pytest.raises(ContractNotFoundError):
        await _account(setup)(uuid4())


def test_rn15_saldo_con_anulados_y_devoluciones() -> None:
    from tests.unit.commercial.contracts.test_contract import _contract

    pending = _contract(advance_cents=100_000)
    assert ContractBalance.of(pending, paid_cents=0, refunded_cents=0).balance_cents == (
        pending.total_cents - 100_000
    )
    pending.status = pending.status.SIGNED
    balance = ContractBalance.of(pending, paid_cents=300_000, refunded_cents=50_000)
    assert balance.balance_cents == pending.total_cents - 300_000 + 50_000
    assert balance.is_overdue(pending.balance_due_date) is False
    assert balance.is_overdue(pending.balance_due_date + timedelta(days=1)) is True
