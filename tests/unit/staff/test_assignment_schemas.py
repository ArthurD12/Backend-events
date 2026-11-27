"""Pruebas de los esquemas Pydantic de asignaciones (HU17, plan §4.2/§4.4).

Cubren la forma del contrato: céntimos enteros, fecha/hora locales, motivo
obligatorio, `extra="forbid"` en la edición, conversión Lima ⇄ UTC y la extensión
`conflicts` del 409. Las reglas de negocio (estado del evento, fecha válida,
función obligatoria, solapes…) viven en el dominio/aplicación y no se duplican.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import UUID

import pytest
from pydantic import ValidationError

from local_eventos.modules.commercial.public_api import EventStatus
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentView,
)
from local_eventos.modules.staff.domain.enums import AssignmentStatus, WorkerFunction
from local_eventos.modules.staff.presentation.assignment_schemas import (
    AssignmentCancel,
    AssignmentConflictOut,
    AssignmentCreate,
    AssignmentOut,
    AssignmentProblem,
    AssignmentUpdate,
)

EVENT_ID = UUID("22222222-2222-2222-2222-222222222222")
WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")
ASSIGNMENT_ID = UUID("33333333-3333-3333-3333-333333333333")

VALID_CREATE: dict[str, object] = {
    "event_id": EVENT_ID,
    "worker_id": WORKER_ID,
    "function": "WAITER",
    "date": "2026-12-01",
    "start_time": "18:00:00",
    "end_time": "23:00:00",
    "pay_cents": 4500,
}

VALID_UPDATE: dict[str, object] = {
    "function": "WAITER",
    "date": "2026-12-01",
    "start_time": "18:00:00",
    "end_time": "23:00:00",
    "pay_cents": 4500,
    "reason": "Corrección del horario",
}


def _view(
    *,
    start_at: datetime,
    end_at: datetime,
    event_code: str | None = "EVT-2026-0012",
    event_status: EventStatus | None = EventStatus.CONFIRMED,
) -> AssignmentView:
    return AssignmentView(
        id=ASSIGNMENT_ID,
        event_id=EVENT_ID,
        worker_id=WORKER_ID,
        worker_name="Ana Quispe",
        function=WorkerFunction.WAITER,
        function_description=None,
        start_at=start_at,
        end_at=end_at,
        pay_cents=4500,
        currency="PEN",
        status=AssignmentStatus.ACTIVE,
        event_code=event_code,
        event_status=event_status,
    )


def test_assignment_create_valido() -> None:
    payload = AssignmentCreate.model_validate(VALID_CREATE)

    assert payload.event_id == EVENT_ID
    assert payload.worker_id == WORKER_ID
    assert payload.function is WorkerFunction.WAITER
    assert payload.function_description is None
    assert payload.date == date(2026, 12, 1)
    assert payload.start_time == time(18, 0)
    assert payload.end_time == time(23, 0)
    assert payload.pay_cents == 4500


def test_assignment_create_sin_funcion_la_copia_el_caso_de_uso() -> None:
    data = {key: value for key, value in VALID_CREATE.items() if key != "function"}

    assert AssignmentCreate.model_validate(data).function is None


@pytest.mark.parametrize("value", [-1, 45.5, 45.0, True])
def test_assignment_create_pay_cents_entero_no_negativo(value: object) -> None:
    with pytest.raises(ValidationError):
        AssignmentCreate.model_validate(dict(VALID_CREATE, pay_cents=value))


def test_assignment_create_pay_cents_cero_permitido() -> None:
    assert AssignmentCreate.model_validate(dict(VALID_CREATE, pay_cents=0)).pay_cents == 0


def test_assignment_create_function_description_limite_120() -> None:
    ok = dict(VALID_CREATE, function="OTHER", function_description="x" * 120)
    assert AssignmentCreate.model_validate(ok).function_description == "x" * 120

    with pytest.raises(ValidationError):
        AssignmentCreate.model_validate(
            dict(VALID_CREATE, function="OTHER", function_description="x" * 121)
        )


def test_assignment_update_valido_recorta_el_motivo() -> None:
    payload = AssignmentUpdate.model_validate(
        dict(VALID_UPDATE, reason="  Corrección del horario  ")
    )

    assert payload.reason == "Corrección del horario"
    assert payload.pay_cents == 4500
    assert payload.worker_id is None
    assert payload.event_id is None


@pytest.mark.parametrize("reason", ["", "   "])
def test_assignment_update_exige_motivo_no_vacio(reason: str) -> None:
    with pytest.raises(ValidationError):
        AssignmentUpdate.model_validate(dict(VALID_UPDATE, reason=reason))


def test_assignment_update_motivo_maximo_500() -> None:
    assert AssignmentUpdate.model_validate(dict(VALID_UPDATE, reason="x" * 500)).reason == "x" * 500

    with pytest.raises(ValidationError):
        AssignmentUpdate.model_validate(dict(VALID_UPDATE, reason="x" * 501))


def test_assignment_update_rechaza_claves_extra() -> None:
    with pytest.raises(ValidationError):
        AssignmentUpdate.model_validate(dict(VALID_UPDATE, unexpected="x"))


@pytest.mark.parametrize("value", [-10, 12.5, True])
def test_assignment_update_pay_cents_estricto(value: object) -> None:
    with pytest.raises(ValidationError):
        AssignmentUpdate.model_validate(dict(VALID_UPDATE, pay_cents=value))


def test_assignment_update_acepta_worker_id_y_event_id_para_el_409() -> None:
    """El esquema los parsea; el router decide el 409 `staff.assignment_immutable`."""
    payload = AssignmentUpdate.model_validate(
        dict(VALID_UPDATE, worker_id=str(WORKER_ID), event_id=str(EVENT_ID))
    )

    assert payload.worker_id == WORKER_ID
    assert payload.event_id == EVENT_ID


def test_assignment_out_from_view_convierte_a_lima_y_conserva_utc() -> None:
    start_at = datetime(2026, 12, 1, 23, 0, tzinfo=UTC)  # 18:00 en Lima
    end_at = datetime(2026, 12, 2, 4, 0, tzinfo=UTC)  # 23:00 en Lima

    schema = AssignmentOut.from_view(_view(start_at=start_at, end_at=end_at))

    assert schema.date == date(2026, 12, 1)
    assert schema.start_time == time(18, 0)
    assert schema.end_time == time(23, 0)
    assert schema.start_at == start_at
    assert schema.end_at == end_at
    assert schema.start_at.tzinfo is UTC
    assert schema.end_at.tzinfo is UTC
    assert schema.currency == "PEN"
    assert schema.status is AssignmentStatus.ACTIVE
    assert schema.event_code == "EVT-2026-0012"
    assert schema.event_status is EventStatus.CONFIRMED
    assert schema.worker_name == "Ana Quispe"


def test_assignment_out_from_view_cruce_de_medianoche() -> None:
    # 01/12 22:00 → 02/12 02:00 en Lima; en UTC ya es 02/12.
    start_at = datetime(2026, 12, 2, 3, 0, tzinfo=UTC)
    end_at = datetime(2026, 12, 2, 7, 0, tzinfo=UTC)

    schema = AssignmentOut.from_view(_view(start_at=start_at, end_at=end_at))

    assert schema.date == date(2026, 12, 1)
    assert schema.start_time == time(22, 0)
    assert schema.end_time == time(2, 0)
    assert schema.start_at == start_at
    assert schema.end_at == end_at


def test_assignment_out_from_view_sin_evento() -> None:
    schema = AssignmentOut.from_view(
        _view(
            start_at=datetime(2026, 12, 1, 23, 0, tzinfo=UTC),
            end_at=datetime(2026, 12, 2, 4, 0, tzinfo=UTC),
            event_code=None,
            event_status=None,
        )
    )

    assert schema.event_code is None
    assert schema.event_status is None


def test_assignment_cancel_exige_motivo() -> None:
    with pytest.raises(ValidationError):
        AssignmentCancel.model_validate({})
    with pytest.raises(ValidationError):
        AssignmentCancel.model_validate({"reason": "   "})

    assert AssignmentCancel.model_validate({"reason": "  Cliente canceló  "}).reason == (
        "Cliente canceló"
    )


def test_assignment_problem_serializa_conflicts() -> None:
    problem = AssignmentProblem(
        title="Conflicto de horario",
        status=409,
        code="staff.assignment_overlap",
        detail="El trabajador ya tiene asignaciones que se superponen.",
        conflicts=[
            AssignmentConflictOut(
                event_code="EVT-2026-0012",
                event_date=date(2026, 12, 1),
                start_time=time(18, 0),
                end_time=time(23, 0),
            )
        ],
    )
    data = problem.model_dump(mode="json")

    assert data["code"] == "staff.assignment_overlap"
    assert data["status"] == 409
    assert data["conflicts"] == [
        {
            "event_code": "EVT-2026-0012",
            "event_date": "2026-12-01",
            "start_time": "18:00:00",
            "end_time": "23:00:00",
        }
    ]


def test_assignment_problem_conflicts_vacio_por_defecto() -> None:
    problem = AssignmentProblem(title="x", status=422, code="staff.x", detail="x")

    assert problem.conflicts == []
