"""Pruebas del agregado `Worker` (HU15). Sin base de datos.

Cubre la matriz de validación (CA-15.15) y la idempotencia de estado (R-STF-15).
"""

from __future__ import annotations

from uuid import UUID

import pytest

from local_eventos.modules.staff.domain.document import Document, DocumentType
from local_eventos.modules.staff.domain.enums import (
    WorkerFunction,
    WorkerStatus,
    WorkerType,
)
from local_eventos.modules.staff.domain.errors import StaffValidationError
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.domain.worker import Worker

WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _register(**overrides: object) -> Worker:
    data: dict[str, object] = {
        "name": "Ana Torres",
        "document_type": DocumentType.DNI,
        "document_number": "44125896",
        "worker_id": WORKER_ID,
    }
    data.update(overrides)
    return Worker.register(**data)  # type: ignore[arg-type]


def test_ca15_1_alta_activa_con_obligatorios() -> None:
    worker = _register()

    assert worker.id == WORKER_ID
    assert worker.name == "Ana Torres"
    assert worker.document == Document(DocumentType.DNI, "44125896")
    assert worker.phone is None
    assert worker.function is None
    assert worker.worker_type is None
    assert worker.rate is None
    assert worker.overtime_applies is False
    assert worker.overtime_rate is None
    assert worker.status is WorkerStatus.ACTIVE


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_nombre_obligatorio(name: str) -> None:
    with pytest.raises(StaffValidationError) as error:
        _register(name=name)
    assert error.value.code == "staff.name_required"


def test_nombre_normaliza_espacios_y_admite_hasta_150() -> None:
    worker = _register(name="  Ana   María   Torres  ")

    assert worker.name == "Ana María Torres"
    assert _register(name="x" * 150).name == "x" * 150


def test_nombre_demasiado_largo() -> None:
    with pytest.raises(StaffValidationError) as error:
        _register(name="x" * 151)
    assert error.value.code == "staff.name_too_long"


def test_ca15_2_documento_invalido() -> None:
    with pytest.raises(StaffValidationError) as error:
        _register(document_number="123")
    assert error.value.code == "staff.document_invalid"


@pytest.mark.parametrize("phone", [None, "", "   "])
def test_telefono_vacio_se_guarda_como_none(phone: str | None) -> None:
    assert _register(phone=phone).phone is None


def test_ca15_22_telefono_solo_digitos_sin_longitud() -> None:
    assert _register(phone=" 987654321 ").phone == "987654321"
    assert _register(phone="1").phone == "1"
    assert _register(phone="123456789012345678901").phone == "123456789012345678901"


@pytest.mark.parametrize("phone", ["987-654-321", "+51987654321", "987 654 321", "12a34"])
def test_telefono_invalido(phone: str) -> None:
    with pytest.raises(StaffValidationError) as error:
        _register(phone=phone)
    assert error.value.code == "staff.phone_invalid"


def test_ca15_25_otro_exige_descripcion() -> None:
    worker = _register(function=WorkerFunction.OTHER, function_description="  jefe   de cocina ")

    assert worker.function is WorkerFunction.OTHER
    assert worker.function_description == "jefe de cocina"


@pytest.mark.parametrize("description", [None, "", "   "])
def test_otro_sin_descripcion_falla(description: str | None) -> None:
    with pytest.raises(StaffValidationError) as error:
        _register(function=WorkerFunction.OTHER, function_description=description)
    assert error.value.code == "staff.function_description_required"


@pytest.mark.parametrize(
    "function",
    [
        None,
        WorkerFunction.COOK,
        WorkerFunction.WAITER,
        WorkerFunction.BARTENDER,
        WorkerFunction.ASSISTANT,
        WorkerFunction.COORDINATOR,
    ],
)
def test_ca15_18_funcion_fija_no_admite_descripcion(
    function: WorkerFunction | None,
) -> None:
    assert _register(function=function).function_description is None

    with pytest.raises(StaffValidationError) as error:
        _register(function=function, function_description="extra")
    assert error.value.code == "staff.function_description_not_allowed"


@pytest.mark.parametrize("worker_type", [None, WorkerType.FIXED, WorkerType.EVENTUAL])
def test_ca15_17_tipo_fijo_o_eventual(worker_type: WorkerType | None) -> None:
    assert _register(worker_type=worker_type).worker_type is worker_type


def test_ca15_20_tarifa_centimos_opcional() -> None:
    assert _register(rate=Money(125050)).rate == Money(125050)
    assert _register(rate=Money(0)).rate == Money(0)


def test_tarifa_no_es_un_importe() -> None:
    with pytest.raises(StaffValidationError) as error:
        _register(rate=125050)
    assert error.value.code == "staff.rate_invalid"


@pytest.mark.parametrize(
    ("overtime_applies", "overtime_rate", "code"),
    [
        (False, None, None),
        (True, Money(1), None),
        (True, Money(1500), None),
        (True, None, "staff.overtime_rate_required"),
        (True, Money(0), "staff.overtime_rate_invalid"),
        (False, Money(100), "staff.overtime_rate_not_allowed"),
    ],
)
def test_ca15_21_hora_extra_condicional(
    overtime_applies: bool, overtime_rate: Money | None, code: str | None
) -> None:
    if code is None:
        worker = _register(overtime_applies=overtime_applies, overtime_rate=overtime_rate)
        assert worker.overtime_applies is overtime_applies
        assert worker.overtime_rate == overtime_rate
        return

    with pytest.raises(StaffValidationError) as error:
        _register(overtime_applies=overtime_applies, overtime_rate=overtime_rate)
    assert error.value.code == code


def test_hora_extra_con_valor_que_no_es_importe() -> None:
    with pytest.raises(StaffValidationError) as error:
        _register(overtime_applies=True, overtime_rate=100)
    assert error.value.code == "staff.overtime_rate_invalid"


def test_update_reemplaza_datos_editables() -> None:
    worker = _register(
        phone="987654321",
        function=WorkerFunction.OTHER,
        function_description="cocina",
        worker_type=WorkerType.FIXED,
        rate=Money(1000),
        overtime_applies=True,
        overtime_rate=Money(200),
    )

    worker.update(
        name="  Ana   María Torres ",
        document_type=DocumentType.CE,
        document_number="001-234 567 890",
        phone=None,
        function=WorkerFunction.OTHER,
        function_description="jefa de cocina",
        worker_type=WorkerType.EVENTUAL,
        rate=Money(2000),
        overtime_applies=True,
        overtime_rate=Money(300),
    )

    assert worker.name == "Ana María Torres"
    assert worker.document == Document(DocumentType.CE, "001234567890")
    assert worker.phone is None
    assert worker.function_description == "jefa de cocina"
    assert worker.worker_type is WorkerType.EVENTUAL
    assert worker.rate == Money(2000)
    assert worker.overtime_rate == Money(300)
    assert worker.status is WorkerStatus.ACTIVE


def test_update_limpia_opcionales_omitidos() -> None:
    worker = _register(
        phone="987654321",
        function=WorkerFunction.COOK,
        worker_type=WorkerType.FIXED,
        rate=Money(1000),
        overtime_applies=True,
        overtime_rate=Money(200),
    )

    worker.update(
        name="Ana Torres",
        document_type=DocumentType.DNI,
        document_number="44125896",
    )

    assert worker.phone is None
    assert worker.function is None
    assert worker.worker_type is None
    assert worker.rate is None
    assert worker.overtime_applies is False
    assert worker.overtime_rate is None


def test_update_valida_antes_de_mutar() -> None:
    worker = _register(phone="987654321", rate=Money(1000))

    with pytest.raises(StaffValidationError) as error:
        worker.update(
            name="",
            document_type=DocumentType.DNI,
            document_number="123",
            phone="abc",
            overtime_applies=True,
        )

    assert error.value.code == "staff.name_required"
    assert worker.name == "Ana Torres"
    assert worker.document == Document(DocumentType.DNI, "44125896")
    assert worker.phone == "987654321"
    assert worker.rate == Money(1000)
    assert worker.overtime_applies is False


def test_transiciones_de_estado_idempotentes() -> None:
    worker = _register()

    assert worker.activate() is False
    assert worker.deactivate() is True
    assert worker.status is WorkerStatus.INACTIVE
    assert worker.deactivate() is False
    assert worker.status is WorkerStatus.INACTIVE
    assert worker.activate() is True
    assert worker.status is WorkerStatus.ACTIVE


def test_ca15_11_sin_metodo_delete() -> None:
    worker = _register()

    assert not hasattr(worker, "delete")
    assert not hasattr(worker, "remove")
