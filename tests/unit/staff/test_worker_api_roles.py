"""Permisos por rol en la API de trabajadores (HU15): admin y eventos gestionan; compras no.

Reutiliza el repositorio en memoria, el reloj fijo y los datos de `test_worker_api`
para no duplicar infraestructura. Montan el router de personal en una app propia
(el registro en `main` es T-18) y sustituyen `get_current_user` por un usuario
con el rol que se prueba, igual que el resto de tests de API del proyecto.
"""

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.presentation.errors import (
    register_error_handlers as register_identity_errors,
)
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.staff.domain.enums import WorkerStatus
from local_eventos.modules.staff.presentation.dependencies import (
    get_clock,
    get_worker_repository,
)
from local_eventos.modules.staff.presentation.errors import register_error_handlers
from local_eventos.modules.staff.presentation.worker_router import router
from tests.unit.current_user import signed_in_as
from tests.unit.staff.test_worker_api import (
    ANA,
    BETO,
    FixedClock,
    InMemoryWorkerRepository,
)

_ROLES_CON_ACCESO = [Role.ADMIN, Role.EVENTS_MANAGER]


@pytest.fixture
def api() -> Iterator[tuple[TestClient, InMemoryWorkerRepository]]:
    repository = InMemoryWorkerRepository()

    async def in_memory() -> InMemoryWorkerRepository:
        return repository

    app = FastAPI()
    app.include_router(router)
    register_error_handlers(app)
    register_identity_errors(app)
    app.dependency_overrides[get_worker_repository] = in_memory
    app.dependency_overrides[get_clock] = FixedClock
    app.dependency_overrides[get_current_user] = signed_in_as(Role.ADMIN)
    with TestClient(app) as client:
        yield client, repository


def _sign_in(client: TestClient, role: Role) -> None:
    client.app.dependency_overrides[get_current_user] = signed_in_as(role)  # type: ignore[attr-defined]


def _register(client: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/v1/staff", json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


@pytest.mark.parametrize("role", _ROLES_CON_ACCESO)
def test_admin_y_eventos_obtienen_2xx_en_las_seis_rutas(
    api: tuple[TestClient, InMemoryWorkerRepository], role: Role
) -> None:
    client, _ = api
    _sign_in(client, role)

    created = _register(client, ANA)
    worker_id = created["id"]

    listed = client.get("/v1/staff")
    fetched = client.get(f"/v1/staff/{worker_id}")
    updated = client.put(
        f"/v1/staff/{worker_id}",
        json={
            "name": "Ana Torres Vargas",
            "document_type": "DNI",
            "document_number": "44125896",
        },
    )
    deactivated = client.post(f"/v1/staff/{worker_id}/deactivate")
    activated = client.post(f"/v1/staff/{worker_id}/activate")

    assert listed.status_code == 200
    assert fetched.status_code == 200
    assert updated.status_code == 200
    assert deactivated.status_code == 200
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"


def test_compras_recibe_403_en_las_seis_rutas_sin_alterar_datos(
    api: tuple[TestClient, InMemoryWorkerRepository],
) -> None:
    client, repository = api
    worker_id = UUID(str(_register(client, ANA)["id"]))
    _sign_in(client, Role.PURCHASING_MANAGER)

    register = client.post("/v1/staff", json=BETO)
    listed = client.get("/v1/staff")
    fetched = client.get(f"/v1/staff/{worker_id}")
    updated = client.put(
        f"/v1/staff/{worker_id}",
        json={
            "name": "Nombre cambiado",
            "document_type": "DNI",
            "document_number": "44125896",
        },
    )
    deactivated = client.post(f"/v1/staff/{worker_id}/deactivate")
    activated = client.post(f"/v1/staff/{worker_id}/activate")

    for response in (register, listed, fetched, updated, deactivated, activated):
        assert response.status_code == 403
        assert response.json()["code"] == "auth.forbidden"

    # El intento de alta como compras no crea el trabajador ni toca al existente.
    assert len(repository.workers) == 1
    stored = repository.workers[worker_id]
    assert stored.name == "Ana Torres"
    assert stored.status == WorkerStatus.ACTIVE


def test_sin_sesion_responde_401(api: tuple[TestClient, InMemoryWorkerRepository]) -> None:
    client, _ = api
    worker_id = _register(client, ANA)["id"]
    del client.app.dependency_overrides[get_current_user]  # type: ignore[attr-defined]

    listed = client.get("/v1/staff")
    fetched = client.get(f"/v1/staff/{worker_id}")

    for response in (listed, fetched):
        assert response.status_code == 401
        assert response.json()["code"] == "auth.not_authenticated"
