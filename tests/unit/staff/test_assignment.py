"""Pruebas del agregado `Assignment` (HU17, R-ASG-1..R-ASG-9). Sin base de datos."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.enums import AssignmentStatus, WorkerFunction
from local_eventos.modules.staff.domain.errors import (
    AssignmentFunctionRequiredError,
    AssignmentPayInvalidError,
    AssignmentScheduleInvalidError,
    StaffValidationError,
)
from local_eventos.modules.staff.domain.money import Money

ASSIGNMENT_ID = UUID("22222222-2222-2222-2222-222222222222")
EVENT_ID = UUID("33333333-3333-3333-3333-333333333333")
WORKER_ID = UUID("44444444-4444-4444-4444-444444444444")
START_AT = datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
END_AT = datetime(2026, 11, 25, 22, 0, tzinfo=UTC)


def _register(**overrides: object) -> Assignment:
    data: dict[str, object] = {
        "event_id": EVENT_ID,
        "worker_id": WORKER_ID,
        "function": WorkerFunction.WAITER,
        "start_at": START_AT,
        "end_at": END_AT,
        "pay": Money(4500),
        "assignment_id": ASSIGNMENT_ID,
    }
    data.update(overrides)
    return Assignment.register(**data)  # type: ignore[arg-type]


def test_alta_valida_nace_activa_y_ocupando() -> None:
    assignment = _register()

    assert assignment.id == ASSIGNMENT_ID
    assert assignment.event_id == EVENT_ID
    assert assignment.worker_id == WORKER_ID
    assert assignment.function is WorkerFunction.WAITER
    assert assignment.function_description is None
    assert assignment.start_at == START_AT
    assert assignment.end_at == END_AT
    assert assignment.pay == Money(4500)
    assert assignment.status is AssignmentStatus.ACTIVE
    assert assignment.occupies is True


def test_alta_acepta_pago_en_centimos_enteros() -> None:
    assignment = _register(pay=0, function=WorkerFunction.COOK)

    assert assignment.pay == Money(0)
    assert assignment.pay.currency == "PEN"


def test_funcion_other_exige_descripcion() -> None:
    assignment = _register(
        function=WorkerFunction.OTHER,
        function_description="  Maître   de ceremonias  ",
    )

    assert assignment.function is WorkerFunction.OTHER
    assert assignment.function_description == "Maître de ceremonias"


@pytest.mark.parametrize("description", [None, "", "   "])
def test_funcion_other_sin_descripcion_es_invalida(description: str | None) -> None:
    with pytest.raises(StaffValidationError) as error:
        _register(function=WorkerFunction.OTHER, function_description=description)

    assert error.value.code == "staff.function_description_required"


def test_descripcion_no_permitida_en_otras_funciones() -> None:
    with pytest.raises(StaffValidationError) as error:
        _register(function=WorkerFunction.COOK, function_description="Parrillero")

    assert error.value.code == "staff.function_description_not_allowed"


@pytest.mark.parametrize("function", [None, "COOK"])
def test_funcion_obligatoria(function: object) -> None:
    with pytest.raises(AssignmentFunctionRequiredError) as error:
        _register(function=function)

    assert error.value.code == "staff.assignment_function_required"


@pytest.mark.parametrize("pay", [-1, -4500, 12.5, "4500", True])
def test_pago_invalido(pay: object) -> None:
    with pytest.raises(AssignmentPayInvalidError) as error:
        _register(pay=pay)

    assert error.value.code == "staff.assignment_pay_invalid"


@pytest.mark.parametrize(
    ("start_at", "end_at"),
    [
        (START_AT, START_AT),
        (END_AT, START_AT),
        (START_AT, START_AT - timedelta(seconds=1)),
    ],
)
def test_ventana_invalida_por_orden(start_at: datetime, end_at: datetime) -> None:
    with pytest.raises(AssignmentScheduleInvalidError):
        _register(start_at=start_at, end_at=end_at)


@pytest.mark.parametrize("naive", [datetime(2026, 11, 25, 14, 0), datetime(2026, 11, 25, 22, 0)])
def test_fechas_deben_incluir_zona(naive: datetime) -> None:
    with pytest.raises(AssignmentScheduleInvalidError):
        _register(start_at=naive, end_at=END_AT)


def test_normaliza_instantes_a_utc() -> None:
    lima = timezone(timedelta(hours=-5))
    assignment = _register(
        start_at=datetime(2026, 11, 25, 9, 0, tzinfo=lima),
        end_at=datetime(2026, 11, 25, 17, 0, tzinfo=lima),
    )

    assert assignment.start_at == START_AT
    assert assignment.end_at == END_AT
    assert assignment.start_at.tzinfo is UTC


def test_claves_inmutables_sin_api_para_cambiarlas() -> None:
    assignment = _register()

    with pytest.raises(AttributeError):
        assignment.event_id = uuid4()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        assignment.worker_id = uuid4()  # type: ignore[misc]

    assert not hasattr(assignment, "delete")
    assert not hasattr(assignment, "set_event_id")
    assert not hasattr(assignment, "set_worker_id")
    assert not hasattr(assignment, "activate")


def test_uuid_de_evento_y_trabajador_obligatorios() -> None:
    with pytest.raises(StaffValidationError) as event_error:
        _register(event_id="no-es-uuid")
    assert event_error.value.code == "staff.assignment_event_invalid"

    with pytest.raises(StaffValidationError) as worker_error:
        _register(worker_id="no-es-uuid")
    assert worker_error.value.code == "staff.assignment_worker_invalid"


def test_update_con_cambios_devuelve_true() -> None:
    assignment = _register()
    new_start = START_AT + timedelta(hours=1)
    new_end = END_AT + timedelta(hours=1)

    changed = assignment.update(
        function=WorkerFunction.BARTENDER,
        start_at=new_start,
        end_at=new_end,
        pay=Money(6000),
    )

    assert changed is True
    assert assignment.function is WorkerFunction.BARTENDER
    assert assignment.start_at == new_start
    assert assignment.end_at == new_end
    assert assignment.pay == Money(6000)


def test_update_sin_cambios_devuelve_false() -> None:
    assignment = _register()

    changed = assignment.update(
        function=WorkerFunction.WAITER,
        start_at=START_AT,
        end_at=END_AT,
        pay=Money(4500),
    )

    assert changed is False


def test_update_invalido_conserva_los_valores_anteriores() -> None:
    assignment = _register()

    with pytest.raises(AssignmentPayInvalidError):
        assignment.update(
            function=WorkerFunction.COOK,
            start_at=START_AT + timedelta(hours=1),
            end_at=END_AT + timedelta(hours=1),
            pay=-1,
        )

    assert assignment.function is WorkerFunction.WAITER
    assert assignment.start_at == START_AT
    assert assignment.end_at == END_AT
    assert assignment.pay == Money(4500)


def test_cancel_es_idempotente_y_libera() -> None:
    assignment = _register()

    assert assignment.cancel() is True
    assert assignment.status is AssignmentStatus.CANCELLED
    assert assignment.occupies is False
    assert assignment.cancel() is False
    assert assignment.status is AssignmentStatus.CANCELLED
    assert assignment.occupies is False


def test_release_no_cambia_el_estado_e_es_idempotente() -> None:
    assignment = _register()

    assert assignment.release() is True
    assert assignment.occupies is False
    assert assignment.status is AssignmentStatus.ACTIVE
    assert assignment.release() is False


def test_release_tras_cancelar_no_hace_nada() -> None:
    assignment = _register()
    assignment.cancel()

    assert assignment.release() is False
    assert assignment.status is AssignmentStatus.CANCELLED


def test_snapshot_tiene_valores_serializables() -> None:
    assignment = _register(
        function=WorkerFunction.OTHER,
        function_description="Bartender de autor",
        pay=Money(7250),
    )

    assert assignment.snapshot() == {
        "function": "OTHER",
        "function_description": "Bartender de autor",
        "start_at": START_AT.isoformat(),
        "end_at": END_AT.isoformat(),
        "pay_cents": 7250,
        "currency": "PEN",
    }
