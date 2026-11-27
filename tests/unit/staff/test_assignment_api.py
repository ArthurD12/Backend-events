"""Pruebas de la API REST de asignaciones (HU17, T-19) sin base de datos.

Montan solo el router de asignaciones en una app FastAPI propia (el registro en
`main` es T-21) y reemplazan los casos de uso por instancias reales sobre un
repositorio en memoria. Cubren alta, listado, detalle, edición, anulación,
errores 404/409/422, la ausencia de `DELETE`, los `operationId` estables y los
permisos básicos por rol.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.presentation.errors import (
    register_error_handlers as register_identity_errors,
)
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.staff.application.assignment_occupancy import AssignmentOccupancy
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentView,
)
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
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import AssignmentAudit
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
from tests.unit.staff.test_assignment_use_cases import (
    EVENT_ID,
    WORKER_ID,
    FakeAssignmentRepository,
    FakeClock,
    FakeEventLookup,
    FakeWorkerLookup,
)

ASSIGNMENTS = "/v1/staff/assignments"
WORKER_NAME = "Ana Pérez"
BODY: dict[str, Any] = {
    "event_id": str(EVENT_ID),
    "worker_id": str(WORKER_ID),
    "date": "2026-12-01",
    "start_time": "18:00:00",
    "end_time": "23:00:00",
    "pay_cents": 4500,
}


class ApiAssignmentRepository(FakeAssignmentRepository):
    """Repositorio en memoria que mantiene la vista de lectura al guardar."""

    def __init__(self, worker_names: dict[UUID, str]) -> None:
        super().__init__()
        self.worker_names = worker_names

    async def save(self, assignment: Assignment, audit: AssignmentAudit) -> None:
        await super().save(assignment, audit)
        self.views[assignment.id] = AssignmentView(
            id=assignment.id,
            event_id=assignment.event_id,
            worker_id=assignment.worker_id,
            worker_name=self.worker_names.get(assignment.worker_id, "Trabajador"),
            function=assignment.function,
            function_description=assignment.function_description,
            start_at=assignment.start_at,
            end_at=assignment.end_at,
            pay_cents=assignment.pay.cents,
            currency=assignment.pay.currency,
            status=assignment.status,
        )


@dataclass
class Api:
    client: TestClient
    repository: ApiAssignmentRepository
    events: FakeEventLookup

    def as_role(self, role: Role) -> None:
        app: FastAPI = self.client.app  # type: ignore[attr-defined]
        app.dependency_overrides[get_current_user] = signed_in_as(role)

    def without_session(self) -> None:
        app: FastAPI = self.client.app  # type: ignore[attr-defined]
        del app.dependency_overrides[get_current_user]


def _build(events: FakeEventLookup, clock: FakeClock) -> Api:
    repository = ApiAssignmentRepository({WORKER_ID: WORKER_NAME})
    workers = FakeWorkerLookup()
    occupancy = AssignmentOccupancy(repository, events)

    app = FastAPI()
    app.include_router(router)
    register_error_handlers(app)
    register_identity_errors(app)
    app.dependency_overrides[get_register_assignment] = lambda: RegisterAssignment(
        repository, workers, events, occupancy, clock
    )
    app.dependency_overrides[get_update_assignment] = lambda: UpdateAssignment(
        repository, workers, events, occupancy, clock
    )
    app.dependency_overrides[get_cancel_assignment] = lambda: CancelAssignment(
        repository, events, clock
    )
    app.dependency_overrides[get_list_event_assignments] = lambda: ListEventAssignments(
        repository, events
    )
    app.dependency_overrides[get_assignment_use_case] = lambda: GetAssignment(repository)
    app.dependency_overrides[get_event_lookup] = lambda: events
    app.dependency_overrides[get_current_user] = signed_in_as(Role.ADMIN)

    client = TestClient(app)
    return Api(client=client, repository=repository, events=events)


@pytest.fixture
def api() -> Iterator[Api]:
    built = _build(FakeEventLookup(), FakeClock())
    with built.client:
        yield built


def _register(api: Api, body: dict[str, Any] | None = None) -> dict[str, Any]:
    response = api.client.post(ASSIGNMENTS, json=body or BODY)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def test_post_crea_201(api: Api) -> None:
    body = _register(api)

    assert body["event_id"] == str(EVENT_ID)
    assert body["event_code"] == "EVT-2026-0012"
    assert body["event_status"] == "CONFIRMED"
    assert body["worker_id"] == str(WORKER_ID)
    assert body["worker_name"] == WORKER_NAME
    assert body["function"] == "WAITER"
    assert body["date"] == "2026-12-01"
    assert body["start_time"] == "18:00:00"
    assert body["end_time"] == "23:00:00"
    assert body["pay_cents"] == 4500
    assert body["currency"] == "PEN"
    assert body["status"] == "ACTIVE"


def test_get_lista_200(api: Api) -> None:
    created = _register(api)

    response = api.client.get(ASSIGNMENTS, params={"event_id": str(EVENT_ID)})

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [created["id"]]


def test_get_detalle_200(api: Api) -> None:
    created = _register(api)

    response = api.client.get(f"{ASSIGNMENTS}/{created['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["worker_name"] == WORKER_NAME
    assert body["event_code"] == "EVT-2026-0012"


def test_put_actualiza_200(api: Api) -> None:
    created = _register(api)

    response = api.client.put(
        f"{ASSIGNMENTS}/{created['id']}",
        json={
            "function": "COOK",
            "date": "2026-12-01",
            "start_time": "19:00:00",
            "end_time": "22:00:00",
            "pay_cents": 5000,
            "reason": "Cambio solicitado por el cliente",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["function"] == "COOK"
    assert body["pay_cents"] == 5000
    assert body["status"] == "ACTIVE"


def test_put_con_worker_o_evento_es_inmutable_409(api: Api) -> None:
    created = _register(api)

    for field, value in (("worker_id", str(uuid4())), ("event_id", str(uuid4()))):
        response = api.client.put(
            f"{ASSIGNMENTS}/{created['id']}",
            json={
                "function": "WAITER",
                "date": "2026-12-01",
                "start_time": "18:00:00",
                "end_time": "23:00:00",
                "pay_cents": 4500,
                "reason": "Intento de cambio",
                field: value,
            },
        )

        assert response.status_code == 409
        assert response.json()["code"] == "staff.assignment_immutable"


def test_cancelar_200(api: Api) -> None:
    created = _register(api)

    response = api.client.post(
        f"{ASSIGNMENTS}/{created['id']}/cancel",
        json={"reason": "El cliente canceló el evento"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "CANCELLED"


def test_no_existe_delete_405(api: Api) -> None:
    created = _register(api)

    response = api.client.delete(f"{ASSIGNMENTS}/{created['id']}")

    assert response.status_code == 405


def test_404_asignacion_inexistente(api: Api) -> None:
    assignment_id = uuid4()

    fetched = api.client.get(f"{ASSIGNMENTS}/{assignment_id}")
    updated = api.client.put(
        f"{ASSIGNMENTS}/{assignment_id}",
        json={
            "function": "WAITER",
            "date": "2026-12-01",
            "start_time": "18:00:00",
            "end_time": "23:00:00",
            "pay_cents": 4500,
            "reason": "Corrección",
        },
    )
    cancelled = api.client.post(
        f"{ASSIGNMENTS}/{assignment_id}/cancel", json={"reason": "Anulación"}
    )

    for response in (fetched, updated, cancelled):
        assert response.status_code == 404
        assert response.json()["code"] == "staff.assignment_not_found"


def test_404_evento_inexistente(api: Api) -> None:
    response = api.client.post(ASSIGNMENTS, json={**BODY, "event_id": str(uuid4())})

    assert response.status_code == 404
    assert response.json()["code"] == "staff.event_not_found"


def test_409_solape_incluye_conflicts(api: Api) -> None:
    _register(api)

    response = api.client.post(ASSIGNMENTS, json=BODY)

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "staff.assignment_overlap"
    assert body["conflicts"] == [
        {
            "event_code": "EVT-2026-0012",
            "event_date": "2026-12-01",
            "start_time": "18:00:00",
            "end_time": "23:00:00",
        }
    ]
    assert "worker_name" not in body["conflicts"][0]
    assert "pay_cents" not in body["conflicts"][0]


def test_422_ventana_invalida(api: Api) -> None:
    response = api.client.post(
        ASSIGNMENTS,
        json={**BODY, "start_time": "18:00:00", "end_time": "18:00:00"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "staff.assignment_schedule_invalid"


def test_operation_ids_estables(api: Api) -> None:
    paths = api.client.app.openapi()["paths"]  # type: ignore[attr-defined]

    expected = {
        (ASSIGNMENTS, "post"): "staff_assignment_register",
        (ASSIGNMENTS, "get"): "staff_assignment_list",
        (f"{ASSIGNMENTS}/{{assignment_id}}", "get"): "staff_assignment_get",
        (f"{ASSIGNMENTS}/{{assignment_id}}", "put"): "staff_assignment_update",
        (f"{ASSIGNMENTS}/{{assignment_id}}/cancel", "post"): "staff_assignment_cancel",
    }
    for (path, method), operation_id in expected.items():
        assert paths[path][method]["operationId"] == operation_id

    assert "delete" not in paths[f"{ASSIGNMENTS}/{{assignment_id}}"]


def test_admin_tiene_2xx(api: Api) -> None:
    created = _register(api)
    assert api.client.get(ASSIGNMENTS, params={"event_id": str(EVENT_ID)}).status_code == 200
    assert api.client.get(f"{ASSIGNMENTS}/{created['id']}").status_code == 200


def test_encargado_de_eventos_lee_pero_no_escribe(api: Api) -> None:
    created = _register(api)
    api.as_role(Role.EVENTS_MANAGER)

    assert api.client.get(ASSIGNMENTS, params={"event_id": str(EVENT_ID)}).status_code == 200
    assert api.client.get(f"{ASSIGNMENTS}/{created['id']}").status_code == 200
    assert api.client.post(ASSIGNMENTS, json=BODY).status_code == 403
    assert (
        api.client.put(
            f"{ASSIGNMENTS}/{created['id']}",
            json={
                "function": "WAITER",
                "date": "2026-12-01",
                "start_time": "18:00:00",
                "end_time": "23:00:00",
                "pay_cents": 4500,
                "reason": "Corrección",
            },
        ).status_code
        == 403
    )
    assert (
        api.client.post(
            f"{ASSIGNMENTS}/{created['id']}/cancel", json={"reason": "Anulación"}
        ).status_code
        == 403
    )


def test_compras_no_accede_ni_a_lectura(api: Api) -> None:
    created = _register(api)
    api.as_role(Role.PURCHASING_MANAGER)

    assert api.client.get(ASSIGNMENTS, params={"event_id": str(EVENT_ID)}).status_code == 403
    assert api.client.get(f"{ASSIGNMENTS}/{created['id']}").status_code == 403
    assert api.client.post(ASSIGNMENTS, json=BODY).status_code == 403


def test_sin_sesion_401(api: Api) -> None:
    api.without_session()

    response = api.client.get(ASSIGNMENTS, params={"event_id": str(EVENT_ID)})

    assert response.status_code == 401
