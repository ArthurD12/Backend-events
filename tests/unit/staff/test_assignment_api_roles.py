"""Matriz de roles y errores de la API de asignaciones (HU17, T-20).

Cubre las cinco rutas (`POST`, `GET` lista, `GET` detalle, `PUT` y `cancel`) con
los tres roles del sistema y sin sesión, la ausencia de `DELETE` y el 409 de
cruce. Reutiliza el repositorio en memoria de T-19 y envuelve los casos de uso de
escritura en un contador para comprobar que una petición denegada no llega a
ejecutarlos.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.presentation.errors import (
    register_error_handlers as register_identity_errors,
)
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.staff.application.assignment_occupancy import AssignmentOccupancy
from local_eventos.modules.staff.application.use_cases.cancel_assignment import (
    CancelAssignment,
)
from local_eventos.modules.staff.application.use_cases.get_assignment import GetAssignment
from local_eventos.modules.staff.application.use_cases.list_event_assignments import (
    ListEventAssignments,
)
from local_eventos.modules.staff.application.use_cases.register_assignment import (
    RegisterAssignment,
)
from local_eventos.modules.staff.application.use_cases.update_assignment import (
    UpdateAssignment,
)
from local_eventos.modules.staff.presentation.assignment_router import router
from local_eventos.modules.staff.presentation.dependencies import (
    get_assignment_use_case,
    get_cancel_assignment,
    get_event_lookup,
    get_list_event_assignments,
    get_register_assignment,
    get_update_assignment,
)
from local_eventos.modules.staff.presentation.errors import register_error_handlers
from tests.unit.current_user import signed_in_as
from tests.unit.staff.test_assignment_api import (
    ASSIGNMENTS,
    BODY,
    WORKER_NAME,
    ApiAssignmentRepository,
)
from tests.unit.staff.test_assignment_use_cases import (
    EVENT_ID,
    WORKER_ID,
    FakeClock,
    FakeEventLookup,
    FakeWorkerLookup,
)

_UPDATE_BODY: dict[str, Any] = {
    "function": "COOK",
    "date": "2026-12-01",
    "start_time": "19:00:00",
    "end_time": "22:00:00",
    "pay_cents": 5000,
    "reason": "Cambio solicitado por el cliente",
}
_CONFLICT_KEYS = {"event_code", "event_date", "start_time", "end_time"}


@dataclass
class _Counters:
    register: int = 0
    update: int = 0
    cancel: int = 0

    def snapshot(self) -> tuple[int, int, int]:
        return self.register, self.update, self.cancel


class _CountingUseCase:
    """Envuelve un caso de uso de escritura y cuenta sus ejecuciones."""

    def __init__(self, inner: Any, counters: _Counters, attribute: str) -> None:
        self.inner = inner
        self.counters = counters
        self.attribute = attribute

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        setattr(self.counters, self.attribute, getattr(self.counters, self.attribute) + 1)
        result: Any = await self.inner.execute(*args, **kwargs)
        return result


@dataclass
class Api:
    client: TestClient
    repository: ApiAssignmentRepository
    counters: _Counters

    def as_role(self, role: Role) -> None:
        app: FastAPI = self.client.app  # type: ignore[attr-defined]
        app.dependency_overrides[get_current_user] = signed_in_as(role)

    def without_session(self) -> None:
        app: FastAPI = self.client.app  # type: ignore[attr-defined]
        del app.dependency_overrides[get_current_user]


def _build() -> Api:
    repository = ApiAssignmentRepository({WORKER_ID: WORKER_NAME})
    workers = FakeWorkerLookup()
    events = FakeEventLookup()
    clock = FakeClock()
    occupancy = AssignmentOccupancy(repository, events)
    counters = _Counters()

    app = FastAPI()
    app.include_router(router)
    register_error_handlers(app)
    register_identity_errors(app)
    app.dependency_overrides[get_register_assignment] = lambda: _CountingUseCase(
        RegisterAssignment(repository, workers, events, occupancy, clock),
        counters,
        "register",
    )
    app.dependency_overrides[get_update_assignment] = lambda: _CountingUseCase(
        UpdateAssignment(repository, workers, events, occupancy, clock),
        counters,
        "update",
    )
    app.dependency_overrides[get_cancel_assignment] = lambda: _CountingUseCase(
        CancelAssignment(repository, events, clock),
        counters,
        "cancel",
    )
    app.dependency_overrides[get_list_event_assignments] = lambda: ListEventAssignments(
        repository, events
    )
    app.dependency_overrides[get_assignment_use_case] = lambda: GetAssignment(repository)
    app.dependency_overrides[get_event_lookup] = lambda: events
    app.dependency_overrides[get_current_user] = signed_in_as(Role.ADMIN)

    return Api(client=TestClient(app), repository=repository, counters=counters)


@pytest.fixture
def api() -> Iterator[Api]:
    built = _build()
    with built.client:
        yield built


def _register(api: Api) -> dict[str, Any]:
    response = api.client.post(ASSIGNMENTS, json=BODY)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _cancel(api: Api, assignment_id: str) -> Any:
    return api.client.post(f"{ASSIGNMENTS}/{assignment_id}/cancel", json={"reason": "Anulación"})


def _list(api: Api) -> Any:
    return api.client.get(ASSIGNMENTS, params={"event_id": str(EVENT_ID)})


def _get(api: Api, assignment_id: str) -> Any:
    return api.client.get(f"{ASSIGNMENTS}/{assignment_id}")


def _put(api: Api, assignment_id: str, body: dict[str, Any] | None = None) -> Any:
    return api.client.put(f"{ASSIGNMENTS}/{assignment_id}", json=body or _UPDATE_BODY)


def test_admin_obtiene_2xx_en_las_cinco_rutas(api: Api) -> None:
    created = _register(api)
    assignment_id = created["id"]

    listed = _list(api)
    fetched = _get(api, assignment_id)
    updated = _put(api, assignment_id)
    cancelled = _cancel(api, assignment_id)

    assert listed.status_code == 200
    assert fetched.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["function"] == "COOK"
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert api.counters.snapshot() == (1, 1, 1)


def test_encargado_de_eventos_lee_pero_no_escribe(api: Api) -> None:
    created = _register(api)
    assignment_id = created["id"]
    api.as_role(Role.EVENTS_MANAGER)
    before = api.counters.snapshot()

    listed = _list(api)
    fetched = _get(api, assignment_id)
    register = api.client.post(ASSIGNMENTS, json=BODY)
    update = _put(api, assignment_id)
    cancel = _cancel(api, assignment_id)

    assert listed.status_code == 200
    assert fetched.status_code == 200
    for response in (register, update, cancel):
        assert response.status_code == 403
        assert response.json()["code"] == "auth.forbidden"
    assert api.counters.snapshot() == before


def test_compras_403_en_las_cinco_rutas_incluida_lectura(api: Api) -> None:
    created = _register(api)
    assignment_id = created["id"]
    api.as_role(Role.PURCHASING_MANAGER)
    before = api.counters.snapshot()

    listed = _list(api)
    fetched = _get(api, assignment_id)
    register = api.client.post(ASSIGNMENTS, json=BODY)
    update = _put(api, assignment_id)
    cancel = _cancel(api, assignment_id)

    for response in (listed, fetched, register, update, cancel):
        assert response.status_code == 403
        assert response.json()["code"] == "auth.forbidden"
    assert api.counters.snapshot() == before


def test_sin_sesion_401_en_las_cinco_rutas(api: Api) -> None:
    created = _register(api)
    assignment_id = created["id"]
    api.without_session()
    before = api.counters.snapshot()

    listed = _list(api)
    fetched = _get(api, assignment_id)
    register = api.client.post(ASSIGNMENTS, json=BODY)
    update = _put(api, assignment_id)
    cancel = _cancel(api, assignment_id)

    for response in (listed, fetched, register, update, cancel):
        assert response.status_code == 401
        assert response.json()["code"] == "auth.not_authenticated"
    assert api.counters.snapshot() == before


def test_delete_responde_405(api: Api) -> None:
    created = _register(api)

    response = api.client.delete(f"{ASSIGNMENTS}/{created['id']}")

    assert response.status_code == 405


def test_409_de_solape_es_problem_details_sin_datos_personales(api: Api) -> None:
    _register(api)

    response = api.client.post(ASSIGNMENTS, json=BODY)

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "staff.assignment_overlap"
    conflicts = body["conflicts"]
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert set(conflict) == _CONFLICT_KEYS
    assert conflict["event_code"] == "EVT-2026-0012"
    assert conflict["event_date"] == "2026-12-01"
    assert conflict["start_time"] == "18:00:00"
    assert conflict["end_time"] == "23:00:00"
    for leaked in (
        "worker_name",
        "document_type",
        "document_number",
        "phone",
        "pay_cents",
        "pay",
        "rate",
    ):
        assert leaked not in conflict
        assert leaked not in response.text


def test_409_de_solape_no_escribe_ni_cuenta_el_alta(api: Api) -> None:
    _register(api)

    response = api.client.post(ASSIGNMENTS, json=BODY)

    assert response.status_code == 409
    # El caso de uso se ejecutó una vez (la segunda alta), pero no persistió.
    assert api.counters.snapshot() == (2, 0, 0)
    assert len(api.repository.assignments) == 1


def test_404_de_asignacion_inexistente_no_depende_del_rol(api: Api) -> None:
    api.as_role(Role.EVENTS_MANAGER)
    assignment_id = uuid4()

    fetched = _get(api, str(assignment_id))
    updated = _put(api, str(assignment_id))
    cancelled = api.client.post(
        f"{ASSIGNMENTS}/{assignment_id}/cancel", json={"reason": "Anulación"}
    )

    # El encargado de eventos no escribe: 403 antes de resolver la asignación.
    assert fetched.status_code == 404
    for response in (updated, cancelled):
        assert response.status_code == 403
