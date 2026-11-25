"""Pago registrado (DOMAIN.md §6): monto positivo, fecha no futura, inmutable."""

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from local_eventos.modules.ledger.domain.payment import (
    LedgerRuleError,
    LedgerValidationError,
    Payment,
    PaymentKind,
    PaymentMethod,
    PaymentVoid,
    format_payment_number,
)

TODAY = date(2026, 11, 22)


def _payment(**changes: object) -> Payment:
    data: dict[str, object] = {
        "number": "PAG-2026-0001",
        "contract_id": uuid4(),
        "kind": PaymentKind.ADVANCE,
        "amount_cents": 272_500,
        "method": PaymentMethod.YAPE_PLIN,
        "reference": "  Op.  123456 ",
        "paid_on": TODAY,
        "recorded_by": uuid4(),
        "now": datetime(2026, 11, 22, 15, tzinfo=UTC),
        "today": TODAY,
        **changes,
    }
    return Payment.record(**data)  # type: ignore[arg-type]


def test_registra_el_pago_con_referencia_limpia() -> None:
    payment = _payment()

    assert (payment.amount_cents, payment.reference) == (272_500, "Op. 123456")


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"amount_cents": 0}, "payment.amount_invalid"),
        ({"paid_on": TODAY + timedelta(days=1)}, "payment.date_in_future"),
        ({"reference": "x" * 101}, "payment.reference_too_long"),
    ],
)
def test_datos_invalidos(changes: dict[str, object], code: str) -> None:
    with pytest.raises(LedgerValidationError) as error:
        _payment(**changes)
    assert error.value.code == code


def test_regla_5_un_pago_no_se_modifica() -> None:
    payment = _payment()
    with pytest.raises(FrozenInstanceError):
        payment.amount_cents = 1  # type: ignore[misc]


def test_ca20_1_numero_pag_por_anio() -> None:
    assert format_payment_number(2026, 7) == "PAG-2026-0007"
    assert _payment(number="PAG-2026-0007").number == "PAG-2026-0007"


def test_ca19_5_un_pago_parcial_se_anula_con_motivo_limpio() -> None:
    payment = _payment(kind=PaymentKind.INSTALLMENT)
    by, now = uuid4(), datetime(2026, 11, 23, tzinfo=UTC)

    void = PaymentVoid.of(payment, reason="  Monto  equivocado ", voided_by=by, now=now)

    assert (void.payment_id, void.reason, void.voided_by, void.voided_at) == (
        payment.id,
        "Monto equivocado",
        by,
        now,
    )


@pytest.mark.parametrize("kind", [PaymentKind.ADVANCE, PaymentKind.REFUND])
def test_ca19_5_el_adelanto_y_la_devolucion_no_se_anulan_por_aqui(kind: PaymentKind) -> None:
    with pytest.raises(LedgerRuleError) as error:
        PaymentVoid.of(_payment(kind=kind), reason="x", voided_by=uuid4(), now=datetime.now(UTC))
    assert error.value.code == "payment.not_voidable"


@pytest.mark.parametrize(
    ("reason", "code"), [("   ", "payment.reason_required"), ("x" * 501, "payment.reason_too_long")]
)
def test_ca19_5_motivo_obligatorio(reason: str, code: str) -> None:
    payment = _payment(kind=PaymentKind.INSTALLMENT)
    with pytest.raises(LedgerValidationError) as error:
        PaymentVoid.of(payment, reason=reason, voided_by=uuid4(), now=datetime.now(UTC))
    assert error.value.code == code
