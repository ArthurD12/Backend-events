"""Pruebas del importe en céntimos del trabajador (HU15, R-STF-7/R-STF-8). Sin base de datos."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from local_eventos.modules.staff.domain.errors import StaffValidationError
from local_eventos.modules.staff.domain.money import CURRENCY, Money


def test_ca15_20_acepta_centimos_y_moneda_pen() -> None:
    money = Money(0)

    assert money.cents == 0
    assert money.currency == "PEN"
    assert money.currency == CURRENCY
    assert Money(125050).cents == 125050


@pytest.mark.parametrize("cents", [True, False, 12.5, "100", None])
def test_rechaza_booleanos_y_no_enteros(cents: object) -> None:
    with pytest.raises(StaffValidationError) as error:
        Money(cents)  # type: ignore[arg-type]
    assert error.value.code == "staff.rate_invalid"


@pytest.mark.parametrize("cents", [-1, -100000])
def test_rechaza_negativos(cents: int) -> None:
    with pytest.raises(StaffValidationError) as error:
        Money(cents)
    assert error.value.code == "staff.rate_invalid"


def test_rechaza_moneda_distinta_de_pen() -> None:
    with pytest.raises(StaffValidationError) as error:
        Money(100, currency="USD")
    assert error.value.code == "staff.rate_invalid"


def test_importe_es_inmutable() -> None:
    money = Money(100)

    with pytest.raises(FrozenInstanceError):
        money.cents = 200  # type: ignore[misc]
