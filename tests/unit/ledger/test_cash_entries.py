"""Consultas de ledger para los reportes (HU31–HU34): caja línea a línea y pagado por contrato."""

from datetime import UTC, date, datetime
from uuid import uuid4

from local_eventos.modules.ledger.application.use_cases.cash import (
    CashEntries,
    CashEntryKind,
    ContractPaidTotalsQuery,
)
from local_eventos.modules.ledger.application.use_cases.movements import (
    MovementRequest,
    RecordMovement,
)
from local_eventos.modules.ledger.application.use_cases.payments import (
    PaymentRequest,
    RecordPayment,
    VoidPayment,
)
from local_eventos.modules.ledger.domain.movement import MovementCategory, MovementType
from local_eventos.modules.ledger.domain.payment import Payment, PaymentKind, PaymentMethod
from local_eventos.modules.ledger.public_api import ContractPaidTotals

from .fakes import FakeLedgerClock, InMemoryMovementRepository, InMemoryPaymentRepository

TODAY = date(2026, 11, 22)
NOW = datetime(2026, 11, 22, 15, tzinfo=UTC)
CONTRACT = uuid4()


async def _pay(
    repo: InMemoryPaymentRepository, kind: PaymentKind, amount: int, day: int, month: int = 11
) -> Payment:
    request = PaymentRequest(
        contract_id=CONTRACT, kind=kind, amount_cents=amount, method=PaymentMethod.CASH,
        reference=None, paid_on=date(2026, month, day), recorded_by=uuid4(),
    )  # fmt: skip
    return await RecordPayment(repo)(request, now=NOW, today=TODAY)


async def test_pagado_y_devuelto_por_contrato_sin_anulados() -> None:
    repo = InMemoryPaymentRepository()
    await _pay(repo, PaymentKind.ADVANCE, 50_000, 1)
    voided = await _pay(repo, PaymentKind.INSTALLMENT, 10_000, 2)
    await _pay(repo, PaymentKind.REFUND, 5_000, 3)
    await VoidPayment(repo)(voided.id, reason="Error", voided_by=uuid4(), now=NOW)
    other = uuid4()

    totals = await ContractPaidTotalsQuery(repo)([CONTRACT, other])

    assert totals == {
        CONTRACT: ContractPaidTotals(paid_cents=50_000, refunded_cents=5_000),
        other: ContractPaidTotals(),
    }


async def test_ca32_2_caja_con_pagos_y_movimientos_y_anulados_marcados() -> None:
    payments, movements = InMemoryPaymentRepository(), InMemoryMovementRepository()
    advance = await _pay(payments, PaymentKind.ADVANCE, 50_000, 5)
    installment = await _pay(payments, PaymentKind.INSTALLMENT, 10_000, 20)
    await VoidPayment(payments)(installment.id, reason="Error", voided_by=uuid4(), now=NOW)
    await _pay(payments, PaymentKind.ADVANCE, 1_000, 30, month=10)  # fuera del rango
    event_id = uuid4()
    await RecordMovement(movements, FakeLedgerClock())(
        MovementRequest(
            type=MovementType.EXPENSE, category=MovementCategory.STAFF, concept="Mozos",
            amount_cents=20_000, method=PaymentMethod.CASH, reference=None,
            occurred_on=date(2026, 11, 10), event_id=event_id, recorded_by=uuid4(),
        )
    )  # fmt: skip

    entries = await CashEntries(payments, movements)(date(2026, 11, 1), date(2026, 11, 22))

    assert [(e.occurred_on.day, e.kind, e.concept, e.amount_cents, e.voided) for e in entries] == [
        (5, CashEntryKind.CLIENT_PAYMENT, advance.number, 50_000, False),
        (10, CashEntryKind.EXPENSE, "Mozos", 20_000, False),
        (20, CashEntryKind.CLIENT_PAYMENT, installment.number, 10_000, True),
    ]
    assert (entries[0].contract_id, entries[0].payment_kind) == (CONTRACT, PaymentKind.ADVANCE)
    assert (entries[1].event_id, entries[1].category) == (event_id, MovementCategory.STAFF)
