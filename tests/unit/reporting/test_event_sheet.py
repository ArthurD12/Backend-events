"""Caso de uso de la ficha consolidada del evento (HU14) con fakes de cada lookup."""

from uuid import uuid4

import pytest

from local_eventos.modules.reporting.application.errors import ReportEventNotFoundError
from local_eventos.modules.reporting.application.use_cases.event_sheet import GetEventSheet

from .sheet_fakes import (
    ACCOUNT,
    AUTHOR,
    COORDINATOR,
    DETAIL,
    EVENT_ID,
    FOLLOW_UP,
    MATERIALS,
    STAFF,
    SheetFakes,
)


def _sheet(fakes: SheetFakes) -> GetEventSheet:
    return GetEventSheet(
        fakes.details, fakes.follow_up, fakes.materials, fakes.accounts, fakes.event_staff,
        fakes.user_names,
    )  # fmt: skip


async def test_ca14_ficha_completa_por_bloques() -> None:
    fakes = SheetFakes(staff=STAFF)

    sheet = await _sheet(fakes)(EVENT_ID, include_account=True)

    assert sheet.event == DETAIL
    assert sheet.staff == STAFF
    assert sheet.materials == MATERIALS
    assert sheet.account == ACCOUNT
    assert sheet.follow_up == FOLLOW_UP
    assert sheet.user_names == {COORDINATOR: "Rosa Huamán", AUTHOR: "Harold Canaza"}


async def test_ca14_5_sin_permiso_de_pagos_no_consulta_la_cuenta() -> None:
    fakes = SheetFakes()

    sheet = await _sheet(fakes)(EVENT_ID, include_account=False)

    assert sheet.account is None
    assert fakes.calls.accounts == []


async def test_ca14_3_sin_modulo_de_personal_el_bloque_es_none() -> None:
    sheet = await _sheet(SheetFakes(staff=None))(EVENT_ID, include_account=True)

    assert sheet.staff is None


async def test_evento_inexistente() -> None:
    with pytest.raises(ReportEventNotFoundError):
        await _sheet(SheetFakes())(uuid4(), include_account=True)
