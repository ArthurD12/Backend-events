"""Casos de uso de ledger con piezas en memoria (HU19–HU22). Sin base de datos."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from local_eventos.modules.ledger.application.errors import (
    MovementAlreadyVoidedError,
    MovementNotFoundError,
    PaymentAlreadyVoidedError,
    PaymentNotFoundError,
)
from local_eventos.modules.ledger.application.ports.movement_repository import (
    MovementFilters,
    MovementState,
)
from local_eventos.modules.ledger.application.use_cases.cash import CashTotals, EventCash
from local_eventos.modules.ledger.application.use_cases.movements import (
    ListMovements,
    MovementRequest,
    RecordMovement,
    VoidMovement,
)
from local_eventos.modules.ledger.application.use_cases.payments import (
    ContractPaymentEntries,
    FindPayment,
    PaymentRequest,
    RecordPayment,
    VoidPayment,
)
from local_eventos.modules.ledger.domain.movement import MovementCategory, MovementType
from local_eventos.modules.ledger.domain.payment import (
    LedgerRuleError,
    LedgerValidationError,
    Payment,
    PaymentKind,
    PaymentMethod,
)

from .fakes import FakeLedgerClock, InMemoryMovementRepository, InMemoryPaymentRepository

TODAY = date(2026, 11, 22)
NOW = datetime(2026, 11, 22, 15, tzinfo=UTC)


async def _pay(
    repo: InMemoryPaymentRepository,
    kind: PaymentKind = PaymentKind.INSTALLMENT,
    amount: int = 10_000,
    paid_on: date = TODAY,
    contract_id: object = None,
) -> Payment:
    request = PaymentRequest(
        contract_id=contract_id or uuid4(),  # type: ignore[arg-type]
        kind=kind,
        amount_cents=amount,
        method=PaymentMethod.CASH,
        reference=None,
        paid_on=paid_on,
        recorded_by=uuid4(),
    )
    return await RecordPayment(repo)(request, now=NOW, today=TODAY)


async def test_ca20_1_cada_pago_recibe_el_siguiente_numero_del_anio() -> None:
    repo = InMemoryPaymentRepository()

    first, second = await _pay(repo), await _pay(repo)

    assert (first.number, second.number) == ("PAG-2026-0001", "PAG-2026-0002")


async def test_un_pago_invalido_no_gasta_numero() -> None:
    repo = InMemoryPaymentRepository()
    with pytest.raises(LedgerValidationError):
        await _pay(repo, amount=0)

    assert (await _pay(repo)).number == "PAG-2026-0001"


async def test_ca19_5_anular_inserta_la_anulacion_y_el_pago_sigue() -> None:
    repo = InMemoryPaymentRepository()
    payment = await _pay(repo)

    entry = await VoidPayment(repo)(payment.id, reason="Error", voided_by=uuid4(), now=NOW)

    assert entry.payment == payment and entry.is_voided
    assert repo.payments == [payment]
    found = await FindPayment(repo)(payment.id)
    assert found is not None and found.void == entry.void
    entries = await ContractPaymentEntries(repo)(payment.contract_id)
    assert [e.is_voided for e in entries] == [True]


async def test_errores_al_anular_un_pago() -> None:
    repo = InMemoryPaymentRepository()
    advance = await _pay(repo, kind=PaymentKind.ADVANCE)
    installment = await _pay(repo)
    void = VoidPayment(repo)
    await void(installment.id, reason="Error", voided_by=uuid4(), now=NOW)

    with pytest.raises(PaymentNotFoundError):
        await void(uuid4(), reason="x", voided_by=uuid4(), now=NOW)
    with pytest.raises(LedgerRuleError):
        await void(advance.id, reason="x", voided_by=uuid4(), now=NOW)
    with pytest.raises(PaymentAlreadyVoidedError):
        await void(installment.id, reason="x", voided_by=uuid4(), now=NOW)


def _movement_request(**changes: object) -> MovementRequest:
    data: dict[str, object] = {
        "type": MovementType.EXPENSE,
        "category": MovementCategory.SUPPLIES,
        "concept": "Insumos",
        "amount_cents": 30_000,
        "method": PaymentMethod.CASH,
        "reference": None,
        "occurred_on": TODAY,
        "event_id": None,
        "recorded_by": uuid4(),
        **changes,
    }
    return MovementRequest(**data)  # type: ignore[arg-type]


async def test_hu21_registrar_anular_y_filtrar_movimientos() -> None:
    repo, clock = InMemoryMovementRepository(), FakeLedgerClock()
    event_id = uuid4()
    supplies = await RecordMovement(repo, clock)(_movement_request(event_id=event_id))
    income = await RecordMovement(repo, clock)(
        _movement_request(type=MovementType.INCOME, category=MovementCategory.OTHER_INCOME)
    )
    voided = await VoidMovement(repo, clock)(
        income.movement.id, reason="Duplicado", voided_by=uuid4()
    )
    listing = ListMovements(repo)

    assert voided.void is not None and voided.void.voided_at == clock.now()
    by_event = await listing(MovementFilters(event_id=event_id))
    assert [e.movement.id for e in by_event.items] == [supplies.movement.id]
    only_voided = await listing(MovementFilters(state=MovementState.VOIDED))
    assert [e.movement.id for e in only_voided.items] == [income.movement.id]
    assert (await listing(MovementFilters(), page_size=500)).page_size == 100


async def test_errores_al_anular_un_movimiento() -> None:
    repo, clock = InMemoryMovementRepository(), FakeLedgerClock()
    entry = await RecordMovement(repo, clock)(_movement_request())
    await VoidMovement(repo, clock)(entry.movement.id, reason="x", voided_by=uuid4())

    with pytest.raises(MovementNotFoundError):
        await VoidMovement(repo, clock)(uuid4(), reason="x", voided_by=uuid4())
    with pytest.raises(MovementAlreadyVoidedError):
        await VoidMovement(repo, clock)(entry.movement.id, reason="x", voided_by=uuid4())


async def test_r_pag_4_movimiento_con_fecha_futura() -> None:
    with pytest.raises(LedgerValidationError):
        await RecordMovement(InMemoryMovementRepository(), FakeLedgerClock())(
            _movement_request(occurred_on=TODAY + timedelta(days=1))
        )


async def test_ca22_sumas_por_mes_sin_anulados() -> None:
    payments, movements, clock = (
        InMemoryPaymentRepository(),
        InMemoryMovementRepository(),
        FakeLedgerClock(),
    )
    await _pay(payments, kind=PaymentKind.ADVANCE, amount=100_000, paid_on=date(2026, 10, 5))
    voided = await _pay(payments, amount=50_000, paid_on=date(2026, 11, 2))
    await VoidPayment(payments)(voided.id, reason="Error", voided_by=uuid4(), now=NOW)
    await _pay(payments, amount=20_000, paid_on=date(2026, 11, 3))
    await _pay(payments, kind=PaymentKind.REFUND, amount=5_000, paid_on=date(2026, 11, 4))
    event_id = uuid4()
    await RecordMovement(movements, clock)(
        _movement_request(occurred_on=date(2026, 11, 10), event_id=event_id)
    )
    gone = await RecordMovement(movements, clock)(
        _movement_request(category=MovementCategory.STAFF, event_id=event_id)
    )
    await VoidMovement(movements, clock)(gone.movement.id, reason="x", voided_by=uuid4())

    months = await CashTotals(payments, movements)(date(2026, 10, 1), date(2026, 11, 30))

    assert [(m.year, m.month) for m in months] == [(2026, 10), (2026, 11)]
    assert (months[0].client_payments_cents, months[0].refunds_cents) == (100_000, 0)
    assert (months[1].client_payments_cents, months[1].refunds_cents) == (20_000, 5_000)
    assert months[1].by_category == {MovementCategory.SUPPLIES: 30_000}
    assert await EventCash(movements)(event_id) == {MovementCategory.SUPPLIES: 30_000}
