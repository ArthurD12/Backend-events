"""Trabajador (HU15): validaciones, edición y estado."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from local_eventos.modules.staff.domain.errors import StaffValidationError
from local_eventos.modules.staff.domain.worker import (
    DocumentType,
    Worker,
    WorkerData,
    WorkerFunction,
    WorkerType,
)

NOW = datetime(2026, 11, 25, 15, tzinfo=UTC)
DATA = WorkerData(
    name="  Rosa   Huamán ",
    document_type=DocumentType.DNI,
    document_number="44125896",
    phone="987 654 321",
    function=WorkerFunction.WAITER,
    worker_type=WorkerType.EVENTUAL,
    reference_rate_cents=12_000,
)


def test_ca15_1_registra_un_trabajador_activo_con_sus_datos_limpios() -> None:
    by = uuid4()

    worker = Worker.register(DATA, created_by=by, now=NOW)

    assert worker.name == "Rosa Huamán"
    assert (worker.document.type, worker.document.number) == (DocumentType.DNI, "44125896")
    assert worker.phone == "987654321"
    assert worker.reference_rate_cents == 12_000
    assert worker.active is True
    assert (worker.created_by, worker.updated_by, worker.created_at) == (by, by, NOW)


def test_carne_de_extranjeria_alfanumerico() -> None:
    data = replace(DATA, document_type=DocumentType.CE, document_number="ab12345678")

    assert Worker.register(data, created_by=uuid4(), now=NOW).document.number == "AB12345678"


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "  "},
        {"name": "x" * 121},
        {"document_number": "1234567"},
        {"document_type": DocumentType.CE, "document_number": "12345678"},
        {"document_type": DocumentType.CE, "document_number": "AB-1234567"},
        {"phone": "98765432"},
        {"phone": "+51987654321"},
        {"reference_rate_cents": -1},
        {"reference_rate_cents": True},
    ],
)
def test_datos_invalidos(changes: dict[str, object]) -> None:
    with pytest.raises(StaffValidationError) as error:
        Worker.register(replace(DATA, **changes), created_by=uuid4(), now=NOW)  # type: ignore[arg-type]

    assert error.value.code == "staff.validation"


def test_tarifa_cero_se_permite() -> None:
    worker = Worker.register(replace(DATA, reference_rate_cents=0), created_by=uuid4(), now=NOW)

    assert worker.reference_rate_cents == 0


def test_ca15_3_modifica_todos_los_datos_y_la_auditoria() -> None:
    worker = Worker.register(DATA, created_by=uuid4(), now=NOW)
    editor = uuid4()
    later = datetime(2026, 11, 26, tzinfo=UTC)

    worker.update(
        replace(
            DATA, name="Rosa H.", function=WorkerFunction.BARTENDER, document_number="44125897"
        ),
        updated_by=editor,
        now=later,
    )

    assert (worker.name, worker.function, worker.document.number) == (
        "Rosa H.",
        WorkerFunction.BARTENDER,
        "44125897",
    )
    assert (worker.updated_by, worker.updated_at) == (editor, later)


def test_si_un_dato_falla_no_cambia_nada() -> None:
    worker = Worker.register(DATA, created_by=uuid4(), now=NOW)

    with pytest.raises(StaffValidationError):
        worker.update(replace(DATA, name="Otra", phone="1"), updated_by=uuid4(), now=NOW)

    assert worker.name == "Rosa Huamán"


def test_ca15_4_se_desactiva_y_activa() -> None:
    worker = Worker.register(DATA, created_by=uuid4(), now=NOW)

    worker.set_active(False, updated_by=uuid4(), now=NOW)
    assert worker.active is False
    worker.set_active(True, updated_by=uuid4(), now=NOW)
    assert worker.active is True
