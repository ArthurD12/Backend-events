"""Pruebas de los esquemas Pydantic del personal (HU15, plan §5.2).

Cubren forma del contrato: enums, céntimos enteros, límite de 120 en la
descripción, serialización y moneda. Las reglas de negocio (nombre, documento,
teléfono, función «otro» y condicional de hora extra) viven en el dominio y no se
duplican aquí.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from local_eventos.modules.staff.application.ports.worker_repository import WorkerPage
from local_eventos.modules.staff.domain.document import DocumentType
from local_eventos.modules.staff.domain.enums import (
    WorkerFunction,
    WorkerStatus,
    WorkerType,
)
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.presentation.worker_schemas import (
    WorkerCreate,
    WorkerOut,
    WorkerPageOut,
    WorkerSummaryOut,
    WorkerUpdate,
)

WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")

VALID_PAYLOAD: dict[str, object] = {
    "name": "Ana Quispe",
    "document_type": "DNI",
    "document_number": "12345678",
    "phone": "987654321",
    "function": "WAITER",
    "worker_type": "FIXED",
    "rate_cents": 4500,
    "overtime_applies": True,
    "overtime_rate_cents": 1200,
}


def _worker(
    *,
    rate: Money | None = None,
    overtime_applies: bool = False,
    overtime_rate: Money | None = None,
    function: WorkerFunction | None = WorkerFunction.WAITER,
    description: str | None = None,
) -> Worker:
    return Worker.register(
        name="Ana Quispe",
        document_type=DocumentType.DNI,
        document_number="12345678",
        phone="987654321",
        function=function,
        function_description=description,
        worker_type=WorkerType.FIXED,
        rate=rate,
        overtime_applies=overtime_applies,
        overtime_rate=overtime_rate,
        worker_id=WORKER_ID,
    )


def test_worker_create_valido() -> None:
    payload = WorkerCreate.model_validate(VALID_PAYLOAD)

    assert payload.name == "Ana Quispe"
    assert payload.document_type is DocumentType.DNI
    assert payload.function is WorkerFunction.WAITER
    assert payload.worker_type is WorkerType.FIXED
    assert payload.rate_cents == 4500
    assert payload.overtime_applies is True
    assert payload.overtime_rate_cents == 1200


def test_worker_create_solo_obligatorios() -> None:
    payload = WorkerCreate.model_validate(
        {"name": "Ana", "document_type": "CE", "document_number": "123456789"}
    )

    assert payload.phone is None
    assert payload.function is None
    assert payload.worker_type is None
    assert payload.rate_cents is None
    assert payload.overtime_applies is False
    assert payload.overtime_rate_cents is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("document_type", "RUC"),
        ("function", "COOKER"),
        ("worker_type", "INTERN"),
    ],
)
def test_worker_create_rechaza_enums_invalidos(field: str, value: str) -> None:
    payload = dict(VALID_PAYLOAD, **{field: value})

    with pytest.raises(ValidationError):
        WorkerCreate.model_validate(payload)


def test_worker_update_reutiliza_las_mismas_reglas() -> None:
    payload = WorkerUpdate.model_validate(VALID_PAYLOAD)

    assert payload.rate_cents == 4500
    with pytest.raises(ValidationError):
        WorkerUpdate.model_validate({"document_type": "DNI", "document_number": "12345678"})


def test_function_description_limite_120() -> None:
    ok = dict(VALID_PAYLOAD, function="OTHER", function_description="x" * 120)
    assert WorkerCreate.model_validate(ok).function_description == "x" * 120

    too_long = dict(VALID_PAYLOAD, function="OTHER", function_description="x" * 121)
    with pytest.raises(ValidationError):
        WorkerCreate.model_validate(too_long)


def test_rate_cents_entero_no_negativo() -> None:
    assert WorkerCreate.model_validate(dict(VALID_PAYLOAD, rate_cents=0)).rate_cents == 0

    with pytest.raises(ValidationError):
        WorkerCreate.model_validate(dict(VALID_PAYLOAD, rate_cents=-1))
    with pytest.raises(ValidationError):
        WorkerCreate.model_validate(dict(VALID_PAYLOAD, rate_cents=45.5))
    with pytest.raises(ValidationError):
        WorkerCreate.model_validate(dict(VALID_PAYLOAD, rate_cents=45.0))
    with pytest.raises(ValidationError):
        WorkerCreate.model_validate(dict(VALID_PAYLOAD, rate_cents=True))


def test_overtime_rate_cents_positivo_si_se_informa() -> None:
    assert (
        WorkerCreate.model_validate(dict(VALID_PAYLOAD, overtime_rate_cents=1)).overtime_rate_cents
        == 1
    )

    with pytest.raises(ValidationError):
        WorkerCreate.model_validate(dict(VALID_PAYLOAD, overtime_rate_cents=0))
    with pytest.raises(ValidationError):
        WorkerCreate.model_validate(dict(VALID_PAYLOAD, overtime_rate_cents=-100))


def test_condicional_de_hora_extra_no_se_duplica_en_el_esquema() -> None:
    """La combinación aplica/monto la valida el dominio con su `staff.*` (422)."""
    WorkerCreate.model_validate(
        {
            "name": "Ana",
            "document_type": "DNI",
            "document_number": "12345678",
            "overtime_applies": True,
        }
    )
    WorkerCreate.model_validate(
        {
            "name": "Ana",
            "document_type": "DNI",
            "document_number": "12345678",
            "overtime_applies": False,
            "overtime_rate_cents": 1200,
        }
    )


def test_worker_out_serializacion_y_currency() -> None:
    worker = _worker(
        rate=Money(4500),
        overtime_applies=True,
        overtime_rate=Money(1200),
    )
    schema = WorkerOut.from_worker(worker)
    data = schema.model_dump(mode="json")

    assert schema.currency == "PEN"
    assert schema.status is WorkerStatus.ACTIVE
    assert data["currency"] == "PEN"
    assert data["document_type"] == "DNI"
    assert data["document_number"] == "12345678"
    assert data["function"] == "WAITER"
    assert data["status"] == "ACTIVE"
    assert data["rate_cents"] == 4500
    assert data["overtime_rate_cents"] == 1200


def test_worker_out_sin_importes() -> None:
    schema = WorkerOut.from_worker(_worker())

    assert schema.rate_cents is None
    assert schema.overtime_rate_cents is None
    assert schema.currency == "PEN"
    assert schema.phone == "987654321"


def test_worker_out_rechaza_currency_distinta() -> None:
    with pytest.raises(ValidationError):
        WorkerOut.model_validate(
            {
                "id": WORKER_ID,
                "name": "Ana",
                "document_type": "DNI",
                "document_number": "12345678",
                "phone": None,
                "function": None,
                "function_description": None,
                "worker_type": None,
                "rate_cents": None,
                "overtime_applies": False,
                "overtime_rate_cents": None,
                "status": "ACTIVE",
                "currency": "USD",
            }
        )


def test_worker_summary_incluye_documento() -> None:
    summary = WorkerSummaryOut.from_worker(_worker())

    assert summary.document_type is DocumentType.DNI
    assert summary.document_number == "12345678"
    assert summary.status is WorkerStatus.ACTIVE


def test_worker_page_out_mapea_pagina() -> None:
    page = WorkerPage(items=[_worker()], total=1, page=1, page_size=20)
    schema = WorkerPageOut.from_page(page)

    assert schema.total == 1
    assert schema.page == 1
    assert schema.page_size == 20
    assert schema.items[0].id == WORKER_ID
