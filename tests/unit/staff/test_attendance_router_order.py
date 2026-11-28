"""Orden de rutas de la asistencia frente a `/v1/staff/{worker_id}` (HU18, T-11).

Usa la aplicación real de `main.create_app()` y reemplaza los casos de uso por
repositorios en memoria, de modo que la prueba dependa del orden de registro de
los routers. Un test por ruta: comprueba que la petición llega a su propio
`operationId` (`staff_attendance_update` / `staff_attendance_history`) y que
**no** devuelve el `422` de path param que produciría caer en `staff_get`
(regresión de orden de HU17).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.staff.application.use_cases.get_attendance_history import (
    GetAttendanceHistory,
)
from local_eventos.modules.staff.application.use_cases.update_attendance import (
    UpdateAttendance,
)
from local_eventos.modules.staff.presentation.attendance_dependencies import (
    get_attendance_history,
    get_update_attendance,
    get_user_names,
)
from tests.unit.current_user import signed_in_as
from tests.unit.staff.test_attendance_api import (
    GET_PATH,
    PATCH_PATH,
    ApiAttendanceRepository,
    ApiWorkers,
    FakeUserNames,
    _history_row,
)
from tests.unit.staff.test_attendance_history import EVENT_A
from tests.unit.staff.test_attendance_history import _worker as history_worker
from tests.unit.staff.test_attendance_update import (
    NOW,
    WORKER_ID,
    FakeClock,
    FakeEventLookup,
    _assignment,
    _event,
)


async def _ready() -> None:
    """Readiness falsa: evita abrir una conexión en el lifespan."""

    return None


@dataclass
class AttendanceApp:
    client: TestClient
    matched_operations: list[str | None]
    repository: ApiAttendanceRepository


def build_attendance_app() -> AttendanceApp:
    app = create_app(readiness_check=_ready)
    repository = ApiAttendanceRepository()
    assignment = _assignment()
    repository.assignments[assignment.assignment_id] = assignment
    repository.rows = [_history_row(event_id=EVENT_A, start_at=NOW)]
    events = FakeEventLookup({EVENT_A: _event(event_date=NOW.date())})
    workers = ApiWorkers({WORKER_ID: history_worker(worker_id=WORKER_ID)})
    matched: list[str | None] = []

    @app.middleware("http")
    async def record_matched_route(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        route = request.scope.get("route")
        matched.append(getattr(route, "operation_id", None))
        return response

    app.dependency_overrides[get_update_attendance] = lambda: UpdateAttendance(
        repository, events, FakeClock(NOW)
    )
    app.dependency_overrides[get_attendance_history] = lambda: GetAttendanceHistory(
        repository, workers, events
    )
    app.dependency_overrides[get_user_names] = lambda: FakeUserNames()
    app.dependency_overrides[get_current_user] = signed_in_as(Role.ADMIN)
    return AttendanceApp(client=TestClient(app), matched_operations=matched, repository=repository)


@pytest.fixture
def app() -> Iterator[AttendanceApp]:
    built = build_attendance_app()
    with built.client:
        yield built


def test_patch_asistencia_se_enruta_a_su_operation_id(app: AttendanceApp) -> None:
    response = app.client.patch(PATCH_PATH, json={"status": "ATTENDED"})

    assert response.status_code == 200, response.text
    # Un 422 aquí significaría que la petición cayó en `/v1/staff/{worker_id}`.
    assert response.status_code != 422, response.text
    assert app.matched_operations[-1] == "staff_attendance_update", response.text


def test_get_historial_se_enruta_a_su_operation_id(app: AttendanceApp) -> None:
    response = app.client.get(GET_PATH)

    assert response.status_code == 200, response.text
    assert response.status_code != 422, response.text
    assert app.matched_operations[-1] == "staff_attendance_history", response.text


def test_operation_ids_publicados_en_openapi(app: AttendanceApp) -> None:
    app_fastapi: FastAPI = app.client.app  # type: ignore[attr-defined]
    paths = app_fastapi.openapi()["paths"]

    assert (
        paths["/v1/staff/assignments/{assignment_id}/attendance"]["patch"]["operationId"]
        == "staff_attendance_update"
    )
    assert (
        paths["/v1/staff/workers/{worker_id}/attendance"]["get"]["operationId"]
        == "staff_attendance_history"
    )
