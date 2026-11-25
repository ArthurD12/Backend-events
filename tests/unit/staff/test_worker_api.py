"""Pruebas de la API REST de trabajadores (HU15) con un repositorio en memoria.

Montan solo el router de personal en una app FastAPI propia: el registro en `main`
es T-18. Sin base de datos. Cubren alta, listado, detalle, edición, cambio de
estado, errores 404/409/422 y la ausencia de `DELETE`.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerPage,
    WorkerRef,
    WorkerRepository,
)
from local_eventos.modules.staff.application.search_text import normalize_name
from local_eventos.modules.staff.domain.audit import WorkerAudit
from local_eventos.modules.staff.domain.document import Document
from local_eventos.modules.staff.domain.enums import WorkerFunction, WorkerStatus
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.presentation.dependencies import (
    get_clock,
    get_worker_repository,
)
from local_eventos.modules.staff.presentation.errors import register_error_handlers
from local_eventos.modules.staff.presentation.worker_router import router
from tests.unit.current_user import signed_in_as

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)

ANA = {
    "name": "Ana Torres",
    "document_type": "DNI",
    "document_number": "44125896",
    "phone": "987654321",
    "function": "COOK",
    "rate_cents": 4500,
}
BETO = {
    "name": "Beto Ruiz",
    "document_type": "DNI",
    "document_number": "12345678",
    "function": "WAITER",
}
CARLA = {
    "name": "Carla Sosa",
    "document_type": "CE",
    "document_number": "123456789",
    "function": "COOK",
}


class FixedClock:
    def now(self) -> datetime:
        return NOW


class InMemoryWorkerRepository:
    """Implementación en memoria del puerto, suficiente para la API."""

    def __init__(self) -> None:
        self.workers: dict[UUID, Worker] = {}
        self.audits: list[WorkerAudit] = []

    async def save(self, worker: Worker, audit: WorkerAudit) -> None:
        self.workers[worker.id] = worker
        self.audits.append(audit)

    async def get(self, worker_id: UUID) -> Worker | None:
        return self.workers.get(worker_id)

    async def get_for_update(self, worker_id: UUID) -> Worker | None:
        return self.workers.get(worker_id)

    async def get_by_document(self, document: Document) -> Worker | None:
        return next(
            (worker for worker in self.workers.values() if worker.document == document),
            None,
        )

    async def search(
        self,
        *,
        text: str,
        function: WorkerFunction | None,
        status: WorkerStatus | None,
        page: int,
        page_size: int,
    ) -> WorkerPage:
        found = [
            worker
            for worker in self.workers.values()
            if (status is None or worker.status == status)
            and (function is None or worker.function == function)
            and (not text or text in normalize_name(worker.name) or text in worker.document.number)
        ]
        found.sort(key=lambda worker: (normalize_name(worker.name), worker.name, str(worker.id)))
        start = (page - 1) * page_size
        return WorkerPage(
            items=found[start : start + page_size],
            total=len(found),
            page=page,
            page_size=page_size,
        )

    async def lookup(self, worker_id: UUID) -> WorkerRef | None:
        worker = self.workers.get(worker_id)
        if worker is None:
            return None
        return WorkerRef(
            id=worker.id,
            name=worker.name,
            function=worker.function,
            function_description=worker.function_description,
            status=worker.status,
        )


@pytest.fixture
def api() -> Iterator[TestClient]:
    repository = InMemoryWorkerRepository()

    async def in_memory() -> WorkerRepository:
        return repository

    app = FastAPI()
    app.include_router(router)
    register_error_handlers(app)
    app.dependency_overrides[get_worker_repository] = in_memory
    app.dependency_overrides[get_clock] = FixedClock
    app.dependency_overrides[get_current_user] = signed_in_as(Role.EVENTS_MANAGER)
    with TestClient(app) as client:
        yield client


def _register(api: TestClient, body: dict[str, object]) -> dict[str, object]:
    response = api.post("/v1/staff", json=body)
    assert response.status_code == 201, response.text
    result: dict[str, object] = response.json()
    return result


def test_ca15_1_registra(api: TestClient) -> None:
    body = _register(api, ANA)

    assert body["name"] == "Ana Torres"
    assert body["document_type"] == "DNI"
    assert body["document_number"] == "44125896"
    assert body["status"] == "ACTIVE"
    assert body["currency"] == "PEN"
    assert body["rate_cents"] == 4500
    assert body["overtime_applies"] is False


def test_ca15_3_409(api: TestClient) -> None:
    _register(api, ANA)

    response = api.post("/v1/staff", json=ANA)

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "staff.document_duplicated"


def test_ca15_2_422(api: TestClient) -> None:
    response = api.post("/v1/staff", json={**ANA, "name": "   "})

    assert response.status_code == 422
    assert response.json()["code"] == "staff.name_required"


def test_ca15_25_422_funcion_otro_sin_descripcion(api: TestClient) -> None:
    response = api.post("/v1/staff", json={**ANA, "function": "OTHER"})

    assert response.status_code == 422
    assert response.json()["code"] == "staff.function_description_required"


def test_ca15_8_query_filtros_y_paginacion(api: TestClient) -> None:
    ana = _register(api, ANA)
    _register(api, BETO)
    carla = _register(api, CARLA)
    api.post(f"/v1/staff/{carla['id']}/deactivate")

    active = api.get("/v1/staff")
    assert active.status_code == 200
    assert [item["name"] for item in active.json()["items"]] == ["Ana Torres", "Beto Ruiz"]
    assert active.json()["total"] == 2

    every = api.get("/v1/staff", params={"status": "ALL"})
    assert every.json()["total"] == 3

    cooks = api.get("/v1/staff", params={"function": "COOK", "status": "ALL"})
    assert [item["name"] for item in cooks.json()["items"]] == ["Ana Torres", "Carla Sosa"]

    by_text = api.get("/v1/staff", params={"text": "ana"})
    assert [item["name"] for item in by_text.json()["items"]] == ["Ana Torres"]

    by_document = api.get("/v1/staff", params={"text": "4412"})
    assert [item["name"] for item in by_document.json()["items"]] == ["Ana Torres"]

    second = api.get("/v1/staff", params={"status": "ALL", "page": 2, "page_size": 1})
    assert second.json()["total"] == 3
    assert second.json()["page"] == 2
    assert second.json()["page_size"] == 1
    assert [item["name"] for item in second.json()["items"]] == ["Beto Ruiz"]

    assert ana["id"] is not None


def test_ca15_7_get_activo_e_inactivo(api: TestClient) -> None:
    worker = _register(api, ANA)

    fetched = api.get(f"/v1/staff/{worker['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["document_number"] == "44125896"

    api.post(f"/v1/staff/{worker['id']}/deactivate")
    inactive = api.get(f"/v1/staff/{worker['id']}")
    assert inactive.status_code == 200
    assert inactive.json()["status"] == "INACTIVE"


def test_ca15_6_put_es_reemplazo_completo(api: TestClient) -> None:
    worker = _register(api, ANA)

    response = api.put(
        f"/v1/staff/{worker['id']}",
        json={
            "name": "Ana Torres Vargas",
            "document_type": "DNI",
            "document_number": "44125896",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Ana Torres Vargas"
    assert body["phone"] is None
    assert body["function"] is None
    assert body["rate_cents"] is None
    assert body["status"] == "ACTIVE"


def test_ca15_10_desactiva_y_reactiva(api: TestClient) -> None:
    worker = _register(api, ANA)

    deactivated = api.post(f"/v1/staff/{worker['id']}/deactivate", json={"reason": "Renuncia"})
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "INACTIVE"
    assert api.get("/v1/staff").json()["items"] == []

    activated = api.post(f"/v1/staff/{worker['id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"


def test_ca15_7_no_encontrado_404(api: TestClient) -> None:
    worker_id = uuid4()

    fetched = api.get(f"/v1/staff/{worker_id}")
    updated = api.put(
        f"/v1/staff/{worker_id}",
        json={
            "name": "Nadie",
            "document_type": "DNI",
            "document_number": "44125896",
        },
    )
    deactivated = api.post(f"/v1/staff/{worker_id}/deactivate")

    for response in (fetched, updated, deactivated):
        assert response.status_code == 404
        assert response.json()["code"] == "staff.not_found"


def test_ca15_11_no_existe_delete(api: TestClient) -> None:
    worker = _register(api, ANA)

    response = api.delete(f"/v1/staff/{worker['id']}")

    assert response.status_code == 405


def test_operation_ids_estables(api: TestClient) -> None:
    schema = api.app.openapi()
    paths = schema["paths"]

    expected = {
        ("/v1/staff", "post"): "staff_register",
        ("/v1/staff", "get"): "staff_search",
        ("/v1/staff/{worker_id}", "get"): "staff_get",
        ("/v1/staff/{worker_id}", "put"): "staff_update",
        ("/v1/staff/{worker_id}/deactivate", "post"): "staff_deactivate",
        ("/v1/staff/{worker_id}/activate", "post"): "staff_activate",
    }
    for (path, method), operation_id in expected.items():
        assert paths[path][method]["operationId"] == operation_id

    assert "delete" not in paths["/v1/staff/{worker_id}"]
