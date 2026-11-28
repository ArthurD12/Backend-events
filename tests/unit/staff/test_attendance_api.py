"""Pruebas de la API de asistencia del personal (HU18, T-11).

Montan solo `attendance_router` en una app FastAPI propia y reemplazan las
dependencias por los casos de uso reales sobre repositorios en memoria. Cubren:

- `PATCH /v1/staff/assignments/{id}/attendance` 200 y 404/409/422 con su `code`
  exacto (CA-18.1/2/3/4/15/16), la forma de `AttendanceOut`, `extra="forbid"` y
  el evento huérfano serializado con campos `null` sin 404 (CA-18.22).
- `GET /v1/staff/workers/{id}/attendance` 200 y 404/422 con su `code`
  (CA-18.5/7/8/15), la forma de `AttendanceHistoryPage`, los alias `from`/`to`
  y el evento huérfano incluido sin filtro y excluido con rango (CA-18.22).

Sin base de datos: fakes en memoria con la semántica de los puertos.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from local_eventos.modules.commercial.public_api import EventInfo, EventStatus
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.presentation.errors import (
    register_error_handlers as register_identity_errors,
)
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.staff.application.ports.attendance_repository import (
    AttendanceAssignmentView,
    AttendanceHistoryRow,
    AttendanceView,
)
from local_eventos.modules.staff.application.ports.worker_repository import WorkerRef
from local_eventos.modules.staff.application.use_cases.get_attendance_history import (
    GetAttendanceHistory,
)
from local_eventos.modules.staff.application.use_cases.update_attendance import (
    UpdateAttendance,
)
from local_eventos.modules.staff.domain.attendance import Attendance, AttendanceStatus
from local_eventos.modules.staff.domain.attendance_audit import AttendanceAudit
from local_eventos.modules.staff.domain.enums import AssignmentStatus
from local_eventos.modules.staff.presentation.attendance_dependencies import (
    get_attendance_history,
    get_update_attendance,
    get_user_names,
)
from local_eventos.modules.staff.presentation.attendance_errors import (
    register_error_handlers,
)
from local_eventos.modules.staff.presentation.attendance_router import router
from local_eventos.modules.staff.presentation.errors import (
    register_error_handlers as register_staff_errors,
)
from tests.unit.current_user import signed_in_as
from tests.unit.staff.test_attendance_history import (
    EVENT_A,
    EVENT_B,
    ORPHAN_EVENT,
    _row,
    _worker,
)
from tests.unit.staff.test_attendance_update import (
    ASSIGNMENT_ID,
    EVENT_ID,
    NOW,
    WORKER_ID,
    FakeClock,
    FakeEventLookup,
    _assignment,
    _event,
)

NOT_DUE_END_AT = datetime(2026, 11, 28, 20, 0, tzinfo=UTC)


def _history_row(*, event_id: UUID, start_at: datetime, **kwargs: Any) -> AttendanceHistoryRow:
    """Fila del historial del trabajador de la ruta (id del módulo de actualización)."""
    return _row(event_id=event_id, start_at=start_at, worker_id=WORKER_ID, **kwargs)


def _event_for(event_id: UUID, event_date: date) -> EventInfo:
    """Evento resuelto con un id concreto (para el historial multidato)."""
    base = _event(event_date=event_date)
    return EventInfo(
        id=event_id,
        code=base.code,
        status=base.status,
        event_date=base.event_date,
        start_time=base.start_time,
        end_time=base.end_time,
    )


PATCH_PATH = f"/v1/staff/assignments/{ASSIGNMENT_ID}/attendance"
GET_PATH = f"/v1/staff/workers/{WORKER_ID}/attendance"
MISSING_ID = UUID("00000000-0000-0000-0000-000000000000")
ACTOR_NAME = "Admin Darze"

OUT_KEYS = {
    "assignment_id",
    "worker_id",
    "worker_name",
    "event_id",
    "event_code",
    "event_status",
    "function",
    "function_description",
    "event_date",
    "start_time",
    "end_time",
    "start_at",
    "end_at",
    "pay_cents",
    "currency",
    "assignment_status",
    "attendance_status",
    "attendance_recorded_at",
    "attendance_recorded_by",
    "attendance_recorded_by_id",
}
PAGE_KEYS = {"items", "total", "page", "page_size"}


class ApiAttendanceRepository:
    """Repositorio en memoria con la semántica de ambos casos de uso."""

    def __init__(self) -> None:
        self.assignments: dict[UUID, AttendanceAssignmentView] = {}
        self.attendance: dict[UUID, AttendanceView] = {}
        self.rows: list[AttendanceHistoryRow] = []
        self.audits: list[AttendanceAudit] = []
        self.saved: list[tuple[Attendance, AttendanceAudit]] = []
        self.history_calls: list[tuple[UUID, UUID | None]] = []

    async def lock_assignment(self, assignment_id: UUID) -> AttendanceAssignmentView | None:
        return self.assignments.get(assignment_id)

    async def get(self, assignment_id: UUID) -> AttendanceView | None:
        return self.attendance.get(assignment_id)

    async def save(self, attendance: Attendance, audit: AttendanceAudit) -> None:
        self.saved.append((attendance, audit))
        self.audits.append(audit)
        self.attendance[attendance.assignment_id] = AttendanceView(
            assignment_id=attendance.assignment_id,
            status=attendance.status,
            recorded_by=attendance.recorded_by,
            recorded_at=attendance.recorded_at,
        )

    async def list_history(
        self,
        worker_id: UUID,
        event_id: UUID | None = None,
    ) -> list[AttendanceHistoryRow]:
        self.history_calls.append((worker_id, event_id))
        rows = [row for row in self.rows if row.worker_id == worker_id]
        if event_id is not None:
            rows = [row for row in rows if row.event_id == event_id]
        return rows


class ApiWorkers:
    """`WorkerLookup` mínimo sobre un diccionario."""

    def __init__(self, workers: dict[UUID, WorkerRef]) -> None:
        self.workers = workers

    async def get(self, worker_id: UUID) -> WorkerRef | None:
        return self.workers.get(worker_id)


class FakeUserNames:
    """Resuelve cualquier actor pedido con un nombre fijo."""

    def __init__(self, name: str = ACTOR_NAME) -> None:
        self.name = name
        self.calls: list[Iterable[UUID]] = []

    async def __call__(self, user_ids: Iterable[UUID]) -> dict[UUID, str]:
        self.calls.append(user_ids)
        return {user_id: self.name for user_id in user_ids}


@dataclass
class Api:
    client: TestClient
    repository: ApiAttendanceRepository
    events: FakeEventLookup

    def as_role(self, role: Role) -> None:
        app: FastAPI = self.client.app  # type: ignore[attr-defined]
        app.dependency_overrides[get_current_user] = signed_in_as(role)


def _build(
    *,
    events: dict[UUID, EventInfo] | None = None,
    assignment: AttendanceAssignmentView | None = None,
    attendance: AttendanceView | None = None,
    rows: list[AttendanceHistoryRow] | None = None,
    workers: dict[UUID, WorkerRef] | None = None,
) -> Api:
    repository = ApiAttendanceRepository()
    if assignment is not None:
        repository.assignments[assignment.assignment_id] = assignment
    if attendance is not None:
        repository.attendance[attendance.assignment_id] = attendance
    repository.rows = rows or []

    event_lookup = FakeEventLookup(events if events is not None else {EVENT_ID: _event()})
    worker_lookup = ApiWorkers(workers if workers is not None else {WORKER_ID: _worker()})

    app = FastAPI()
    app.include_router(router)
    register_staff_errors(app)
    register_error_handlers(app)
    register_identity_errors(app)
    app.dependency_overrides[get_update_attendance] = lambda: UpdateAttendance(
        repository, event_lookup, FakeClock(NOW)
    )
    app.dependency_overrides[get_attendance_history] = lambda: GetAttendanceHistory(
        repository, worker_lookup, event_lookup
    )
    app.dependency_overrides[get_user_names] = lambda: FakeUserNames()
    app.dependency_overrides[get_current_user] = signed_in_as(Role.ADMIN)
    return Api(client=TestClient(app), repository=repository, events=event_lookup)


@pytest.fixture
def api() -> Iterator[Api]:
    built = _build(assignment=_assignment())
    with built.client:
        yield built


def _stored(status: AttendanceStatus = AttendanceStatus.ATTENDED) -> AttendanceView:
    return AttendanceView(
        assignment_id=ASSIGNMENT_ID,
        status=status,
        recorded_by=UUID("99999999-9999-9999-9999-999999999999"),
        recorded_at=NOW,
    )


# --- PATCH 200 --------------------------------------------------------------


def test_patch_200_primer_registro_con_evento(api: Api) -> None:
    response = api.client.patch(PATCH_PATH, json={"status": "ATTENDED"})

    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == OUT_KEYS
    assert data["assignment_id"] == str(ASSIGNMENT_ID)
    assert data["worker_id"] == str(WORKER_ID)
    assert data["worker_name"] == "Ana Pérez"
    assert data["event_id"] == str(EVENT_ID)
    assert data["event_code"] == "EV-0001"
    assert data["event_status"] == EventStatus.SCHEDULED
    assert data["event_date"] == "2026-11-28"
    assert data["function"] == "WAITER"
    assert data["pay_cents"] == 15000
    assert data["currency"] == "PEN"
    assert data["assignment_status"] == AssignmentStatus.ACTIVE
    assert data["attendance_status"] == "ATTENDED"
    assert data["attendance_recorded_at"] == "2026-11-28T18:00:00Z"
    assert data["attendance_recorded_by"] == ACTOR_NAME
    assert data["attendance_recorded_by_id"] is not None
    # El primer registro no altera función, horario ni pago (CA-18.1).
    assert data["start_at"] == "2026-11-28T13:00:00Z"
    assert data["end_at"] == "2026-11-28T17:00:00Z"
    assert len(api.repository.audits) == 1


# --- PATCH 404/409/422 ------------------------------------------------------


@pytest.mark.parametrize(
    ("assignment", "attendance", "body", "status_code", "code"),
    [
        (None, None, {"status": "ATTENDED"}, 404, "staff.assignment_not_found"),
        (
            _assignment(end_at=NOT_DUE_END_AT),
            None,
            {"status": "ATTENDED"},
            409,
            "staff.attendance_not_due",
        ),
        (
            _assignment(status=AssignmentStatus.CANCELLED),
            None,
            {"status": "ATTENDED"},
            409,
            "staff.attendance_assignment_cancelled",
        ),
        (
            _assignment(),
            None,
            {"status": "UNKNOWN"},
            422,
            "staff.attendance_status_invalid",
        ),
        (
            _assignment(),
            None,
            {},
            422,
            "staff.attendance_status_invalid",
        ),
        (
            _assignment(),
            _stored(),
            {"status": "NOT_ATTENDED"},
            422,
            "staff.attendance_reason_required",
        ),
    ],
)
def test_patch_errores_con_code_exacto(
    assignment: AttendanceAssignmentView | None,
    attendance: AttendanceView | None,
    body: dict[str, Any],
    status_code: int,
    code: str,
) -> None:
    built = _build(assignment=assignment, attendance=attendance)
    with built.client:
        response = built.client.patch(PATCH_PATH, json=body)

    assert response.status_code == status_code, response.text
    assert response.json()["code"] == code


def test_patch_409_no_guarda_ni_audita() -> None:
    built = _build(assignment=_assignment(end_at=datetime(2026, 11, 28, 20, 0, tzinfo=NOW.tzinfo)))
    with built.client:
        response = built.client.patch(PATCH_PATH, json={"status": "ATTENDED"})

    assert response.status_code == 409, response.text
    assert built.repository.saved == []


def test_patch_extra_field_es_422(api: Api) -> None:
    response = api.client.patch(PATCH_PATH, json={"status": "ATTENDED", "bogus": 1})

    assert response.status_code == 422, response.text


def test_patch_correccion_con_motivo_200(api: Api) -> None:
    api.repository.attendance[ASSIGNMENT_ID] = _stored()

    response = api.client.patch(
        PATCH_PATH, json={"status": "NOT_ATTENDED", "reason": "  se retiró antes  "}
    )

    assert response.status_code == 200, response.text
    assert response.json()["attendance_status"] == "NOT_ATTENDED"
    assert api.repository.audits[0].reason == "se retiró antes"


# --- PATCH evento huérfano --------------------------------------------------


def test_patch_evento_huerfano_serializa_null_sin_404() -> None:
    built = _build(events={}, assignment=_assignment())
    with built.client:
        response = built.client.patch(PATCH_PATH, json={"status": "NOT_ATTENDED"})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["event_code"] is None
    assert data["event_date"] is None
    assert data["event_status"] is None
    assert data["event_id"] == str(EVENT_ID)
    assert data["attendance_status"] == "NOT_ATTENDED"


# --- GET 200 ----------------------------------------------------------------


def test_get_200_forma_de_pagina(api: Api) -> None:
    api.repository.rows = [
        _history_row(
            event_id=EVENT_A,
            start_at=NOW,
            attendance_status=AttendanceStatus.ATTENDED,
            recorded_at=NOW,
            recorded_by=UUID("99999999-9999-9999-9999-999999999999"),
        )
    ]
    api.events.events = {EVENT_A: _event_for(EVENT_A, NOW.date())}

    response = api.client.get(f"/v1/staff/workers/{WORKER_ID}/attendance")

    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == PAGE_KEYS
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert set(data["items"][0]) == OUT_KEYS
    assert data["items"][0]["attendance_status"] == "ATTENDED"
    assert data["items"][0]["attendance_recorded_by"] == ACTOR_NAME


def test_get_200_sin_registro_es_null(api: Api) -> None:
    api.repository.rows = [_history_row(event_id=EVENT_A, start_at=NOW)]
    api.events.events = {EVENT_A: _event_for(EVENT_A, NOW.date())}

    response = api.client.get(f"/v1/staff/workers/{WORKER_ID}/attendance")

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["attendance_status"] is None
    assert item["attendance_recorded_at"] is None
    assert item["attendance_recorded_by"] is None


def test_get_filtra_por_from_y_to(api: Api) -> None:
    api.repository.rows = [
        _history_row(event_id=EVENT_A, start_at=NOW),
        _history_row(event_id=EVENT_B, start_at=NOW),
    ]
    api.events.events = {
        EVENT_A: _event_for(EVENT_A, NOW.date()),
        EVENT_B: _event_for(EVENT_B, NOW.date().replace(day=3)),
    }

    response = api.client.get(
        f"/v1/staff/workers/{WORKER_ID}/attendance",
        params={"from": NOW.date().isoformat(), "to": NOW.date().isoformat()},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["event_id"] == str(EVENT_A)


# --- GET 404/422 ------------------------------------------------------------


def test_get_404_trabajador_inexistente() -> None:
    built = _build(workers={})
    with built.client:
        response = built.client.get(GET_PATH)

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "staff.worker_not_found"


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-12-02", "to": "2026-12-01"},
        {"page": "0"},
        {"page_size": "101"},
        {"page_size": "0"},
    ],
)
def test_get_422_rango_invalido(api: Api, params: dict[str, str]) -> None:
    response = api.client.get(GET_PATH, params=params)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "staff.attendance_date_range_invalid"


# --- GET evento huérfano ----------------------------------------------------


def test_get_evento_huerfano_incluido_sin_filtro() -> None:
    built = _build(
        events={},
        rows=[_history_row(event_id=ORPHAN_EVENT, start_at=NOW)],
    )
    with built.client:
        response = built.client.get(GET_PATH)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["event_id"] == str(ORPHAN_EVENT)
    assert item["event_code"] is None
    assert item["event_date"] is None
    assert item["event_status"] is None


def test_get_evento_huerfano_excluido_con_rango() -> None:
    built = _build(
        events={},
        rows=[_history_row(event_id=ORPHAN_EVENT, start_at=NOW)],
    )
    with built.client:
        response = built.client.get(
            GET_PATH,
            params={"from": NOW.date().isoformat(), "to": NOW.date().isoformat()},
        )

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0


def test_get_evento_huerfano_incluido_con_event_id() -> None:
    built = _build(
        events={},
        rows=[_history_row(event_id=ORPHAN_EVENT, start_at=NOW)],
    )
    with built.client:
        response = built.client.get(GET_PATH, params={"event_id": str(ORPHAN_EVENT)})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["event_code"] is None
    assert built.repository.history_calls == [(WORKER_ID, ORPHAN_EVENT)]
