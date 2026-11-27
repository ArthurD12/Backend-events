"""Colisión de rutas: `/v1/staff/availability` y `/v1/staff/unavailability` frente a
`/v1/staff/{worker_id}` (HU16, T-16; CA-16.17 provisional).

Usa la aplicación real de `main.create_app()` y sustituye los casos de uso por
repositorios en memoria, de modo que la prueba dependa del orden de registro de
los routers y no de una app de juguete. Comprueba dos cosas:

1. Las cinco rutas literales responden con su propio `operationId` (nunca con el
   `422` de path param que produciría caer en `staff_get`).
2. En `app.router.routes` cada ruta literal aparece antes que
   `/v1/staff/{worker_id}`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.identity.domain.permissions import Permission, Role, permissions_of
from local_eventos.modules.identity.public_api import CurrentUser, get_current_user
from local_eventos.modules.staff.application.use_cases.cancel_unavailability import (
    CancelUnavailability,
)
from local_eventos.modules.staff.application.use_cases.get_staff_availability import (
    GetStaffAvailability,
)
from local_eventos.modules.staff.application.use_cases.list_unavailability import (
    ListUnavailability,
)
from local_eventos.modules.staff.application.use_cases.register_unavailability import (
    RegisterUnavailability,
)
from local_eventos.modules.staff.application.use_cases.update_unavailability import (
    UpdateUnavailability,
)
from local_eventos.modules.staff.presentation.dependencies import (
    get_cancel_unavailability,
    get_clock,
    get_list_unavailability,
    get_register_unavailability,
    get_staff_availability_use_case,
    get_update_unavailability,
)
from tests.unit.staff.test_availability_api import (
    AVAILABILITY,
    BODY,
    MISSING_ID,
    UNAVAILABILITY,
    WORKER_ID,
    ApiAssignmentRepository,
    ApiConflictLookup,
    ApiUnavailabilityRepository,
    ApiWorkerRepository,
    _no_event,
    _worker,
)
from tests.unit.staff.test_unavailability_use_cases import FakeClock, FakeWorkerLookup

UPDATE_BODY: dict[str, Any] = {
    "kind": "LEAVE",
    "date": "2026-12-02",
    "start_time": "08:00:00",
    "end_time": "12:00:00",
    "reason": "Cambio de fecha",
}

WORKER_PATH = "/v1/staff/{worker_id}"

_LITERAL_ROUTES: list[tuple[str, str]] = [
    ("GET", AVAILABILITY),
    ("GET", UNAVAILABILITY),
    ("POST", UNAVAILABILITY),
    ("PUT", f"{UNAVAILABILITY}/{{unavailability_id}}"),
    ("POST", f"{UNAVAILABILITY}/{{unavailability_id}}/cancel"),
]

_REQUESTS: list[tuple[str, str, dict[str, Any] | None, dict[str, str] | None, int, str]] = [
    (
        "GET",
        AVAILABILITY,
        None,
        {"from_date": "2026-12-01", "to_date": "2026-12-01"},
        200,
        "staff_availability_get",
    ),
    ("GET", UNAVAILABILITY, None, None, 200, "staff_unavailability_list"),
    ("POST", UNAVAILABILITY, BODY, None, 201, "staff_unavailability_register"),
    (
        "PUT",
        f"{UNAVAILABILITY}/{MISSING_ID}",
        UPDATE_BODY,
        None,
        404,
        "staff_unavailability_update",
    ),
    (
        "POST",
        f"{UNAVAILABILITY}/{MISSING_ID}/cancel",
        {"reason": "Error"},
        None,
        404,
        "staff_unavailability_cancel",
    ),
]


async def _ready() -> None:
    """Comprobación de disponibilidad falsa: evita abrir una conexión en el lifespan."""

    return None


@dataclass
class AvailabilityApp:
    """App real con los casos de uso de disponibilidad en memoria."""

    client: TestClient
    repository: ApiUnavailabilityRepository
    matched_operations: list[str | None]

    def as_role(self, role: Role) -> None:
        app: FastAPI = self.client.app  # type: ignore[attr-defined]
        app.dependency_overrides[get_current_user] = _signed_in_as(role)

    def as_permissions(self, permissions: frozenset[Permission]) -> None:
        app: FastAPI = self.client.app  # type: ignore[attr-defined]
        user = CurrentUser(
            id=uuid4(),
            name="Usuario de prueba",
            role=Role.ADMIN,
            permissions=permissions,
        )

        async def current_user() -> CurrentUser:
            return user

        app.dependency_overrides[get_current_user] = current_user

    def without_session(self) -> None:
        app: FastAPI = self.client.app  # type: ignore[attr-defined]
        del app.dependency_overrides[get_current_user]


def _signed_in_as(role: Role) -> Callable[[], Awaitable[CurrentUser]]:
    user = CurrentUser(
        id=uuid4(),
        name=f"Prueba {role}",
        role=role,
        permissions=permissions_of(role),
    )

    async def current_user() -> CurrentUser:
        return user

    return current_user


def build_availability_app() -> AvailabilityApp:
    """Monta `create_app()` con las dependencias de disponibilidad reemplazadas."""

    app = create_app(readiness_check=_ready)
    repository = ApiUnavailabilityRepository()
    workers = {WORKER_ID: _worker()}
    worker_lookup = FakeWorkerLookup(workers)
    worker_repository = ApiWorkerRepository(list(workers.values()))
    clock = FakeClock()
    matched: list[str | None] = []

    @app.middleware("http")
    async def record_matched_route(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        route = request.scope.get("route")
        matched.append(getattr(route, "operation_id", None))
        return response

    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_staff_availability_use_case] = lambda: GetStaffAvailability(
        worker_repository,
        repository,
        ApiAssignmentRepository(),
        _no_event,
        ApiConflictLookup(),
    )
    app.dependency_overrides[get_register_unavailability] = lambda: RegisterUnavailability(
        worker_lookup, repository, clock
    )
    app.dependency_overrides[get_list_unavailability] = lambda: ListUnavailability(repository)
    app.dependency_overrides[get_update_unavailability] = lambda: UpdateUnavailability(
        repository, clock
    )
    app.dependency_overrides[get_cancel_unavailability] = lambda: CancelUnavailability(
        repository, clock
    )
    app.dependency_overrides[get_current_user] = _signed_in_as(Role.ADMIN)
    return AvailabilityApp(
        client=TestClient(app),
        repository=repository,
        matched_operations=matched,
    )


@pytest.fixture
def availability_app() -> Iterator[AvailabilityApp]:
    built = build_availability_app()
    with built.client:
        yield built


@pytest.mark.parametrize(
    ("method", "path", "body", "params", "expected", "operation_id"),
    _REQUESTS,
)
def test_ruta_literal_responde_con_su_operation_id(
    availability_app: AvailabilityApp,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    params: dict[str, str] | None,
    expected: int,
    operation_id: str,
) -> None:
    response = availability_app.client.request(method, path, json=body, params=params)

    assert response.status_code == expected, response.text
    # Un 422 de path param significaría que la petición cayó en `/v1/staff/{worker_id}`.
    assert response.status_code != 422, response.text
    assert availability_app.matched_operations[-1] == operation_id, response.text


def test_availability_no_se_enruta_a_staff_get(availability_app: AvailabilityApp) -> None:
    response = availability_app.client.get(
        AVAILABILITY, params={"from_date": "2026-12-01", "to_date": "2026-12-01"}
    )

    assert response.status_code == 200, response.text
    assert availability_app.matched_operations[-1] == "staff_availability_get"
    assert availability_app.matched_operations[-1] != "staff_get"


def _declaration_order(app: FastAPI) -> list[Any]:
    """Aplana los routers incluidos en el orden en que el enrutador los evalúa.

    FastAPI agrupa cada `include_router` en una entrada diferida; el orden de las
    entradas y el de sus candidatos es el orden real de resolución.
    """

    ordered: list[Any] = []
    for entry in app.router.routes:
        candidates = getattr(entry, "effective_candidates", None)
        if callable(candidates):
            ordered.extend(candidates())
        else:
            ordered.append(entry)
    return ordered


def test_rutas_literales_declaradas_antes_del_path_param_de_trabajador() -> None:
    app = create_app()
    routes = _declaration_order(app)

    def indexes(path: str, method: str) -> list[int]:
        return [
            index
            for index, route in enumerate(routes)
            if getattr(route, "path", None) == path and method in getattr(route, "methods", set())
        ]

    worker_indexes = indexes(WORKER_PATH, "GET")
    assert worker_indexes, f"no se registró {WORKER_PATH}"
    worker_index = min(worker_indexes)

    for method, path in _LITERAL_ROUTES:
        literal_indexes = indexes(path, method)
        assert literal_indexes, f"no se registró {method} {path}"
        assert min(literal_indexes) < worker_index, (
            f"{method} {path} se registró después de {WORKER_PATH}"
        )
