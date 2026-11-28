"""Pruebas de los esquemas y del contrato de query de asistencia (HU18, T-10).

Cubren la forma observable: `AttendanceUpdate` con `extra="forbid"` y `status`
opcional (la validación real es del caso de uso), `AttendanceOut` con los campos
de evento **anulables** (evento huérfano, R-ATT-23), la serialización de
`AttendanceHistoryPage` con `event_*` en `null` y los alias `from`/`to` de la
consulta del historial (spec §7).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import UUID

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError

from local_eventos.modules.commercial.public_api import EventInfo, EventStatus
from local_eventos.modules.staff.application.ports.attendance_repository import (
    AttendanceAssignmentView,
    AttendanceHistoryRow,
)
from local_eventos.modules.staff.domain.attendance import AttendanceStatus
from local_eventos.modules.staff.domain.enums import AssignmentStatus, WorkerFunction
from local_eventos.modules.staff.presentation.attendance_router import router
from local_eventos.modules.staff.presentation.attendance_schemas import (
    AttendanceHistoryPage,
    AttendanceOut,
    AttendanceUpdate,
)

ASSIGNMENT_ID = UUID("33333333-3333-3333-3333-333333333333")
EVENT_ID = UUID("22222222-2222-2222-2222-222222222222")
WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")
ACTOR_ID = UUID("44444444-4444-4444-4444-444444444444")

START_AT = datetime(2026, 12, 1, 23, 0, tzinfo=UTC)  # 18:00 en Lima
END_AT = datetime(2026, 12, 2, 4, 0, tzinfo=UTC)  # 23:00 en Lima


def _assignment() -> AttendanceAssignmentView:
    return AttendanceAssignmentView(
        assignment_id=ASSIGNMENT_ID,
        event_id=EVENT_ID,
        worker_id=WORKER_ID,
        worker_name="Ana Quispe",
        function=WorkerFunction.WAITER,
        function_description=None,
        start_at=START_AT,
        end_at=END_AT,
        pay_cents=4500,
        currency="PEN",
        assignment_status=AssignmentStatus.ACTIVE,
    )


def _event() -> EventInfo:
    return EventInfo(
        id=EVENT_ID,
        code="EVT-2026-0012",
        status=EventStatus.CONFIRMED,
        event_date=date(2026, 12, 1),
        start_time=time(18, 0),
        end_time=time(23, 0),
    )


def _out(event: EventInfo | None, status: AttendanceStatus | None) -> AttendanceOut:
    return AttendanceOut.from_parts(
        assignment=_assignment(),
        attendance_status=status,
        recorded_at=START_AT if status is not None else None,
        recorded_by=ACTOR_ID if status is not None else None,
        recorded_by_name="Admin Darze" if status is not None else None,
        event=event,
    )


def test_attendance_update_vacio_lo_valida_el_caso_de_uso() -> None:
    payload = AttendanceUpdate.model_validate({})

    assert payload.status is None
    assert payload.reason is None


@pytest.mark.parametrize("status", ["ATTENDED", "NOT_ATTENDED", "OTRO"])
def test_attendance_update_acepta_el_estado_como_texto(status: str) -> None:
    """El esquema no valida el enum: el caso de uso devuelve `staff.attendance_status_invalid`."""
    assert AttendanceUpdate.model_validate({"status": status}).status == status


def test_attendance_update_rechaza_claves_extra() -> None:
    with pytest.raises(ValidationError):
        AttendanceUpdate.model_validate({"status": "ATTENDED", "unexpected": "x"})


def test_attendance_update_documenta_el_enum_en_openapi() -> None:
    schema = AttendanceUpdate.model_json_schema()
    properties = schema["properties"]

    assert properties["status"]["enum"] == ["ATTENDED", "NOT_ATTENDED"]


def test_attendance_out_con_evento_resuelto() -> None:
    schema = _out(_event(), AttendanceStatus.ATTENDED)

    assert schema.event_code == "EVT-2026-0012"
    assert schema.event_status is EventStatus.CONFIRMED
    assert schema.event_date == date(2026, 12, 1)
    assert schema.start_time == time(18, 0)
    assert schema.end_time == time(23, 0)
    assert schema.start_at == START_AT
    assert schema.end_at == END_AT
    assert schema.pay_cents == 4500
    assert schema.currency == "PEN"
    assert schema.attendance_status is AttendanceStatus.ATTENDED
    assert schema.attendance_recorded_by == "Admin Darze"
    assert schema.attendance_recorded_by_id == ACTOR_ID


def test_attendance_out_evento_huerfano_anula_campos_sin_404() -> None:
    schema = _out(None, AttendanceStatus.NOT_ATTENDED)

    assert schema.event_id == EVENT_ID
    assert schema.event_code is None
    assert schema.event_status is None
    assert schema.event_date is None
    assert schema.attendance_status is AttendanceStatus.NOT_ATTENDED


def test_attendance_out_sin_registro_anula_asistencia() -> None:
    schema = _out(None, None)

    assert schema.attendance_status is None
    assert schema.attendance_recorded_at is None
    assert schema.attendance_recorded_by is None
    assert schema.attendance_recorded_by_id is None


def test_attendance_history_page_serializa_evento_nulo() -> None:
    row = AttendanceHistoryRow(
        assignment_id=ASSIGNMENT_ID,
        event_id=EVENT_ID,
        worker_id=WORKER_ID,
        worker_name="Ana Quispe",
        function=WorkerFunction.WAITER,
        function_description=None,
        start_at=START_AT,
        end_at=END_AT,
        pay_cents=4500,
        currency="PEN",
        assignment_status=AssignmentStatus.ACTIVE,
        attendance_status=None,
        recorded_at=None,
        recorded_by=None,
    )
    page = AttendanceHistoryPage(
        items=[
            AttendanceOut.from_parts(
                assignment=row,
                attendance_status=row.attendance_status,
                recorded_at=row.recorded_at,
                recorded_by=row.recorded_by,
                recorded_by_name=None,
                event=None,
            )
        ],
        total=1,
        page=1,
        page_size=20,
    )
    data = page.model_dump(mode="json")

    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 20
    item = data["items"][0]
    assert item["event_code"] is None
    assert item["event_status"] is None
    assert item["event_date"] is None
    assert item["attendance_status"] is None
    assert item["attendance_recorded_by"] is None
    assert item["attendance_recorded_by_id"] is None
    assert item["start_at"] == "2026-12-01T23:00:00Z"


def _route(operation_id: str) -> APIRoute:
    for route in router.routes:
        if isinstance(route, APIRoute) and route.operation_id == operation_id:
            return route
    raise AssertionError(f"No se encontró la ruta {operation_id}")


def test_historial_usa_alias_from_y_to() -> None:
    aliases = {param.alias for param in _route("staff_attendance_history").dependant.query_params}

    assert {"from", "to", "event_id", "page", "page_size"} <= aliases


def test_rutas_documentan_los_operation_id_del_contrato() -> None:
    assert (
        _route("staff_attendance_update").path == "/v1/staff/assignments/{assignment_id}/attendance"
    )
    assert _route("staff_attendance_history").path == "/v1/staff/workers/{worker_id}/attendance"
