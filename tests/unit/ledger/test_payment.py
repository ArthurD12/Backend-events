"""Pago registrado (DOMAIN.md §6): monto positivo, fecha no futura, inmutable."""

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from local_eventos.modules.ledger.domain.payment import (
    LedgerValidationError,
    Payment,
    PaymentKind,
    PaymentMethod,
)

TODAY = date(2026, 11, 22)


def _payment(**changes: object) -> Payment:
    data: dict[str, object] = {
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
