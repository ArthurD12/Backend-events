"""Ingreso o egreso de caja (HU21, RN16): categoría según el tipo, fecha no futura, inmutable."""

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from local_eventos.modules.ledger.domain.movement import (
    CashMovement,
    MovementCategory,
    MovementType,
    MovementVoid,
)
from local_eventos.modules.ledger.domain.payment import LedgerValidationError, PaymentMethod

TODAY = date(2026, 11, 22)


def _movement(**changes: object) -> CashMovement:
    data: dict[str, object] = {
        "type": MovementType.EXPENSE,
        "category": MovementCategory.SUPPLIES,
        "concept": "  Carne  y verduras ",
        "amount_cents": 85_000,
        "method": PaymentMethod.CASH,
        "reference": None,
        "occurred_on": TODAY,
        "event_id": uuid4(),
        "recorded_by": uuid4(),
        "now": datetime(2026, 11, 22, 15, tzinfo=UTC),
        "today": TODAY,
        **changes,
    }
    return CashMovement.record(**data)  # type: ignore[arg-type]


def test_ca21_1_egreso_de_insumos_asociado_a_un_evento() -> None:
    movement = _movement()

    assert (movement.concept, movement.amount_cents) == ("Carne y verduras", 85_000)


def test_ca21_2_ingreso_que_no_es_pago_de_cliente_sin_evento() -> None:
    movement = _movement(
        type=MovementType.INCOME, category=MovementCategory.OTHER_INCOME, event_id=None
    )

    assert movement.type is MovementType.INCOME and movement.event_id is None


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"category": MovementCategory.OTHER_INCOME}, "movement.category_invalid"),
        (
            {"type": MovementType.INCOME, "category": MovementCategory.STAFF},
            "movement.category_invalid",
        ),
        ({"concept": "  "}, "movement.concept_required"),
        ({"concept": "x" * 201}, "movement.concept_too_long"),
        ({"amount_cents": 0}, "movement.amount_invalid"),
        ({"occurred_on": TODAY + timedelta(days=1)}, "movement.date_in_future"),
        ({"reference": "x" * 101}, "movement.reference_too_long"),
    ],
)
def test_datos_invalidos(changes: dict[str, object], code: str) -> None:
    with pytest.raises(LedgerValidationError) as error:
        _movement(**changes)
    assert error.value.code == code


def test_ca21_3_se_anula_con_motivo_y_no_se_edita() -> None:
    movement = _movement()

    void = MovementVoid.of(movement, reason=" Duplicado ", voided_by=uuid4(), now=datetime.now(UTC))

    assert (void.movement_id, void.reason) == (movement.id, "Duplicado")
    with pytest.raises(FrozenInstanceError):
        movement.amount_cents = 1  # type: ignore[misc]
    with pytest.raises(LedgerValidationError) as error:
        MovementVoid.of(movement, reason="", voided_by=uuid4(), now=datetime.now(UTC))
    assert error.value.code == "movement.reason_required"
