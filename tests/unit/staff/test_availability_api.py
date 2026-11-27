"""Pruebas de la API de disponibilidad del personal (HU16, T-15).

Montan solo `availability_router` en una app FastAPI propia y reemplazan las
dependencias por casos de uso reales sobre repositorios en memoria. Cubren las
cinco rutas (200/201/404/409/422), la ausencia de `DELETE` (405), los permisos
(401 sin sesión, 403 para encargado de eventos y compras) y que las respuestas
nunca incluyan pago, tarifa, documento ni teléfono.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from local_eventos.modules.commercial.public_api import EventInfo
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.presentation.errors import (
    register_error_handlers as register_identity_errors,
)
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.staff.application.ports.assignment_conflict_lookup import (
    AssignmentFunction,
)
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentOverlap,
)
from local_eventos.modules.staff.application.ports.worker_repository import WorkerRef
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
from local_eventos.modules.staff.domain.enums import (
    UnavailabilityKind,
    UnavailabilityStatus,
    WorkerFunction,
    WorkerStatus,
)
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.unavailability_audit import UnavailabilityAudit
from local_eventos.modules.staff.presentation.availability_router import router
from local_eventos.modules.staff.presentation.dependencies import (
    get_cancel_unavailability,
    get_clock,
    get_list_unavailability,
    get_register_unavailability,
    get_staff_availability_use_case,
    get_update_unavailability,
)
from local_eventos.modules.staff.presentation.errors import register_error_handlers
from tests.unit.current_user import signed_in_as
from tests.unit.staff.test_unavailability_use_cases import (
    FakeClock,
    FakeWorkerLookup,
)

AVAILABILITY = "/v1/staff/availability"
UNAVAILABILITY = "/v1/staff/unavailability"
WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
MISSING_ID = UUID("33333333-3333-3333-3333-333333333333")
UNAVAILABILITY_ID = UUID("44444444-4444-4444-4444-444444444444")
CANCELLED_ID = UUID("55555555-5555-5555-5555-555555555555")
NOW = FakeClock().now()
SENSITIVE = {"pay", "pay_cents", "rate", "rate_cents", "document", "document_number", "phone"}
BODY: dict[str, Any] = {
    "worker_id": str(WORKER_ID),
    "date": "2026-12-01",
    "start_time": "18:00:00",
    "end_time": "23:00:00",
    "kind": "VACATION",
}


def _worker(worker_id: UUID = WORKER_ID, status: WorkerStatus = WorkerStatus.ACTIVE) -> WorkerRef:
    return WorkerRef(
        id=worker_id,
        name="Ana Torres",
        function=WorkerFunction.WAITER,
        function_description=None,
        status=status,
    )


def _unavailability(
    unavailability_id: UUID = UNAVAILABILITY_ID,
    *,
    status: UnavailabilityStatus = UnavailabilityStatus.ACTIVE,
) -> Unavailability:
    item = Unavailability.register(
        worker_id=WORKER_ID,
        kind=UnavailabilityKind.VACATION,
        start_at=datetime(2026, 12, 1, 23, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 2, 4, 0, tzinfo=UTC),
        unavailability_id=unavailability_id,
    )
    if status is UnavailabilityStatus.CANCELLED:
        item.cancel()
    return item


class ApiUnavailabilityRepository:
    """Repositorio en memoria con la semántica del puerto."""

    def __init__(self) -> None:
        self.items: dict[UUID, Unavailability] = {}
        self.audits: list[UnavailabilityAudit] = []

    async def save(self, unavailability: Unavailability, audit: UnavailabilityAudit) -> None:
        self.items[unavailability.id] = unavailability
        self.audits.append(audit)

    async def get(self, unavailability_id: UUID) -> Unavailability | None:
        return self.items.get(unavailability_id)

    async def get_for_update(self, unavailability_id: UUID) -> Unavailability | None:
        return self.items.get(unavailability_id)

    async def list_active_overlapping(
        self,
        start_at: datetime,
        end_at: datetime,
        worker_ids: Sequence[UUID],
    ) -> list[Unavailability]:
        return [
            item
            for item in self.items.values()
            if item.worker_id in worker_ids
            and item.status is UnavailabilityStatus.ACTIVE
            and item.start_at < end_at
            and item.end_at > start_at
        ]

    async def list_by_worker(
        self,
        worker_id: UUID,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[Unavailability]:
        return [
            item
            for item in self.items.values()
            if item.worker_id == worker_id
            and (start_at is None or item.end_at > start_at)
            and (end_at is None or item.start_at < end_at)
        ]

    async def list(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[Unavailability]:
        return [
            item
            for item in self.items.values()
            if (start_at is None or item.end_at > start_at)
            and (end_at is None or item.start_at < end_at)
        ]


class ApiWorkerRepository:
    """Solo `list_active`, como el contrato que usa la consulta (HU16)."""

    def __init__(self, workers: list[WorkerRef]) -> None:
        self.workers = workers

    async def list_active(self, function: WorkerFunction | None = None) -> list[WorkerRef]:
        return [
            worker
            for worker in self.workers
            if worker.status is WorkerStatus.ACTIVE
            and (function is None or worker.function is function)
        ]


class ApiAssignmentRepository:
    """Sin asignaciones: la prueba de API no necesita solapes."""

    async def list_active_overlaps(
        self,
        worker_id: UUID,
        start_at: datetime,
        end_at: datetime,
        *,
        exclude_assignment_id: UUID | None = None,
    ) -> list[AssignmentOverlap]:
        return []


class ApiConflictLookup:
    async def by_ids(self, assignment_ids: Sequence[UUID]) -> dict[UUID, AssignmentFunction | None]:
        return {}


async def _no_event(event_id: UUID) -> EventInfo | None:
    return None


@dataclass
class Api:
    client: TestClient
    repository: ApiUnavailabilityRepository
    workers: dict[UUID, WorkerRef]

    def as_role(self, role: Role) -> None:
        app: FastAPI = self.client.app  # type: ignore[attr-defined]
        app.dependency_overrides[get_current_user] = signed_in_as(role)

    def without_session(self) -> None:
        app: FastAPI = self.client.app  # type: ignore[attr-defined]
        del app.dependency_overrides[get_current_user]


def _build(workers: dict[UUID, WorkerRef]) -> Api:
    repository = ApiUnavailabilityRepository()
    worker_lookup = FakeWorkerLookup(workers)
    worker_repository = ApiWorkerRepository(list(workers.values()))
    clock = FakeClock()

    app = FastAPI()
    app.include_router(router)
    register_error_handlers(app)
    register_identity_errors(app)
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
    app.dependency_overrides[get_current_user] = signed_in_as(Role.ADMIN)
    return Api(client=TestClient(app), repository=repository, workers=workers)


@pytest.fixture
def api() -> Iterator[Api]:
    built = _build({WORKER_ID: _worker()})
    with built.client:
        yield built


def _assert_no_sensitive(payload: Any) -> None:
    if isinstance(payload, dict):
        assert not (SENSITIVE & set(payload)), payload
        for value in payload.values():
            _assert_no_sensitive(value)
    elif isinstance(payload, list):
        for value in payload:
            _assert_no_sensitive(value)


# --- GET /availability ------------------------------------------------------


def test_get_availability_200(api: Api) -> None:
    response = api.client.get(
        AVAILABILITY, params={"from_date": "2026-12-01", "to_date": "2026-12-01"}
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["from"] == "2026-12-01T05:00:00Z"
    assert data["to"] == "2026-12-02T05:00:00Z"
    assert [item["state"] for item in data["items"]] == ["FREE"]
    _assert_no_sensitive(data)


def test_get_availability_422_ventana_invalida(api: Api) -> None:
    response = api.client.get(
        AVAILABILITY,
        params={
            "from_date": "2026-12-01",
            "to_date": "2026-12-01",
            "start_time": "18:00:00",
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "staff.availability_window_invalid"


def test_get_availability_422_rango_demasiado_grande(api: Api) -> None:
    response = api.client.get(
        AVAILABILITY, params={"from_date": "2026-12-01", "to_date": "2027-01-05"}
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "staff.availability_range_too_large"


# --- GET /unavailability ----------------------------------------------------


def test_get_unavailability_200(api: Api) -> None:
    api.repository.items[UNAVAILABILITY_ID] = _unavailability()

    response = api.client.get(UNAVAILABILITY, params={"worker_id": str(WORKER_ID)})

    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == str(UNAVAILABILITY_ID)
    assert "created_at" not in data["items"][0]
    assert "updated_at" not in data["items"][0]
    _assert_no_sensitive(data)


def test_get_unavailability_422_una_sola_fecha(api: Api) -> None:
    response = api.client.get(UNAVAILABILITY, params={"from_date": "2026-12-01"})

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "staff.availability_window_invalid"


# --- POST /unavailability ---------------------------------------------------


def test_post_unavailability_201(api: Api) -> None:
    response = api.client.post(UNAVAILABILITY, json=BODY)

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["worker_id"] == str(WORKER_ID)
    assert data["status"] == "ACTIVE"
    assert data["date"] == "2026-12-01"
    assert data["start_time"] == "18:00:00"
    assert data["end_time"] == "23:00:00"
    assert len(api.repository.audits) == 1
    _assert_no_sensitive(data)


def test_post_unavailability_404_trabajador(api: Api) -> None:
    response = api.client.post(UNAVAILABILITY, json={**BODY, "worker_id": str(MISSING_ID)})

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "staff.not_found"


def test_post_unavailability_409_trabajador_inactivo() -> None:
    built = _build({WORKER_ID: _worker(status=WorkerStatus.INACTIVE)})
    with built.client:
        response = built.client.post(UNAVAILABILITY, json=BODY)

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "staff.worker_inactive"


def test_post_unavailability_422_tipo_otro_sin_descripcion(api: Api) -> None:
    response = api.client.post(UNAVAILABILITY, json={**BODY, "kind": "OTHER"})

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "staff.unavailability_description_required"


# --- PUT /unavailability/{id} ----------------------------------------------


def _update_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "kind": "LEAVE",
        "date": "2026-12-02",
        "start_time": "08:00:00",
        "end_time": "12:00:00",
        "reason": "Cambio de fecha",
    }
    body.update(overrides)
    return body


def test_put_unavailability_200(api: Api) -> None:
    api.repository.items[UNAVAILABILITY_ID] = _unavailability()

    response = api.client.put(f"{UNAVAILABILITY}/{UNAVAILABILITY_ID}", json=_update_body())

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["kind"] == "LEAVE"
    assert data["date"] == "2026-12-02"
    assert len(api.repository.audits) == 1
    _assert_no_sensitive(data)


def test_put_unavailability_404(api: Api) -> None:
    response = api.client.put(f"{UNAVAILABILITY}/{MISSING_ID}", json=_update_body())

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "staff.unavailability_not_found"


def test_put_unavailability_409_anulada(api: Api) -> None:
    api.repository.items[CANCELLED_ID] = _unavailability(
        CANCELLED_ID, status=UnavailabilityStatus.CANCELLED
    )

    response = api.client.put(f"{UNAVAILABILITY}/{CANCELLED_ID}", json=_update_body())

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "staff.unavailability_cancelled"


def test_put_unavailability_422_sin_motivo(api: Api) -> None:
    api.repository.items[UNAVAILABILITY_ID] = _unavailability()

    response = api.client.put(f"{UNAVAILABILITY}/{UNAVAILABILITY_ID}", json=_update_body(reason=""))

    assert response.status_code == 422, response.text


# --- POST cancel ------------------------------------------------------------


def test_post_cancel_200(api: Api) -> None:
    api.repository.items[UNAVAILABILITY_ID] = _unavailability()

    response = api.client.post(
        f"{UNAVAILABILITY}/{UNAVAILABILITY_ID}/cancel", json={"reason": "Error de registro"}
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "CANCELLED"
    assert api.repository.items[UNAVAILABILITY_ID].status is UnavailabilityStatus.CANCELLED
    _assert_no_sensitive(data)


def test_post_cancel_404(api: Api) -> None:
    response = api.client.post(f"{UNAVAILABILITY}/{MISSING_ID}/cancel", json={"reason": "Error"})

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "staff.unavailability_not_found"


def test_post_cancel_422_sin_motivo(api: Api) -> None:
    api.repository.items[UNAVAILABILITY_ID] = _unavailability()

    response = api.client.post(
        f"{UNAVAILABILITY}/{UNAVAILABILITY_ID}/cancel", json={"reason": "   "}
    )

    assert response.status_code == 422, response.text


# --- DELETE prohibido -------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        AVAILABILITY,
        UNAVAILABILITY,
        f"{UNAVAILABILITY}/{UNAVAILABILITY_ID}",
        f"{UNAVAILABILITY}/{UNAVAILABILITY_ID}/cancel",
    ],
)
def test_delete_responde_405(api: Api, path: str) -> None:
    response = api.client.delete(path)

    assert response.status_code == 405, response.text


# --- Autenticación y permisos ----------------------------------------------


_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", AVAILABILITY, None),
    ("GET", UNAVAILABILITY, None),
    ("POST", UNAVAILABILITY, BODY),
    ("PUT", f"{UNAVAILABILITY}/{UNAVAILABILITY_ID}", _update_body()),
    ("POST", f"{UNAVAILABILITY}/{UNAVAILABILITY_ID}/cancel", {"reason": "Error"}),
]


def _call(api: Api, method: str, path: str, body: dict[str, Any] | None) -> Any:
    params = {"from_date": "2026-12-01", "to_date": "2026-12-01"} if path == AVAILABILITY else None
    return api.client.request(method, path, json=body, params=params)


@pytest.mark.parametrize(("method", "path", "body"), _ROUTES)
def test_sin_sesion_401(api: Api, method: str, path: str, body: dict[str, Any] | None) -> None:
    api.without_session()

    response = _call(api, method, path, body)

    assert response.status_code == 401, response.text


@pytest.mark.parametrize("role", [Role.EVENTS_MANAGER, Role.PURCHASING_MANAGER])
@pytest.mark.parametrize(("method", "path", "body"), _ROUTES)
def test_roles_sin_permiso_403(
    api: Api, role: Role, method: str, path: str, body: dict[str, Any] | None
) -> None:
    api.as_role(role)

    response = _call(api, method, path, body)

    assert response.status_code == 403, response.text


def test_operacion_id_estable(api: Api) -> None:
    app: FastAPI = api.client.app  # type: ignore[attr-defined]
    paths = app.openapi()["paths"]

    assert paths[AVAILABILITY]["get"]["operationId"] == "staff_availability_get"
    assert paths[UNAVAILABILITY]["get"]["operationId"] == "staff_unavailability_list"
    assert paths[UNAVAILABILITY]["post"]["operationId"] == "staff_unavailability_register"
    assert (
        paths[f"{UNAVAILABILITY}/{{unavailability_id}}"]["put"]["operationId"]
        == "staff_unavailability_update"
    )
    assert (
        paths[f"{UNAVAILABILITY}/{{unavailability_id}}/cancel"]["post"]["operationId"]
        == "staff_unavailability_cancel"
    )


def test_horario_local_se_convierte_a_utc(api: Api) -> None:
    response = api.client.post(UNAVAILABILITY, json=BODY)

    data = response.json()
    assert data["start_at"] == "2026-12-01T23:00:00Z"
    assert data["end_at"] == "2026-12-02T04:00:00Z"
    assert "updated_at" not in data


def test_hora_sin_zona_valida(api: Api) -> None:
    response = api.client.get(
        AVAILABILITY,
        params={
            "from_date": "2026-12-01",
            "to_date": "2026-12-01",
            "start_time": "18:00:00",
            "end_time": "23:00:00",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["from"] == "2026-12-01T23:00:00Z"
    assert response.json()["to"] == "2026-12-02T04:00:00Z"
