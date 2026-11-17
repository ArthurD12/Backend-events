"""Pruebas de la API de clientes (HU04) con el repositorio en memoria. Sin base de datos."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.commercial.application.clients.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.commercial.presentation.dependencies import get_client_repository

from .fakes import InMemoryClientRepository

FAMILIA_QUISPE = {
    "name": "Familia Quispe Mamani",
    "document_type": "DNI",
    "document_number": "44125896",
    "phone": "987 654 321",
}


async def _no_database() -> None:
    return None


@pytest.fixture
def api() -> Iterator[TestClient]:
    repository = InMemoryClientRepository()

    async def in_memory() -> ClientRepository:
        return repository

    app = create_app(readiness_check=_no_database)
    app.dependency_overrides[get_client_repository] = in_memory
    with TestClient(app) as client:
        yield client


def test_hu04_registra_un_cliente(api: TestClient) -> None:
    response = api.post("/v1/clients", json=FAMILIA_QUISPE)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Familia Quispe Mamani"
    assert body["phone"] == "987654321"
    assert body["active"] is True


def test_hu04_documento_duplicado_responde_409_con_su_code(api: TestClient) -> None:
    api.post("/v1/clients", json=FAMILIA_QUISPE)

    response = api.post("/v1/clients", json=FAMILIA_QUISPE)

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "client.document_duplicated"


def test_hu04_dato_invalido_responde_422_con_su_code(api: TestClient) -> None:
    response = api.post("/v1/clients", json={**FAMILIA_QUISPE, "document_number": "123"})

    assert response.status_code == 422
    assert response.json()["code"] == "client.document_invalid"


def test_hu04_busca_sin_tildes(api: TestClient) -> None:
    api.post("/v1/clients", json={**FAMILIA_QUISPE, "name": "José Ramírez"})

    response = api.get("/v1/clients", params={"text": "jose ramirez"})

    assert response.status_code == 200
    assert [c["name"] for c in response.json()] == ["José Ramírez"]


def test_hu04_actualiza_contacto_y_lee_la_ficha(api: TestClient) -> None:
    client_id = api.post("/v1/clients", json=FAMILIA_QUISPE).json()["id"]

    updated = api.put(
        f"/v1/clients/{client_id}",
        json={"name": "Familia Quispe", "phone": "912345678", "address": "SJL, Lima"},
    )
    fetched = api.get(f"/v1/clients/{client_id}")

    assert updated.status_code == 200
    assert fetched.json()["address"] == "SJL, Lima"
    assert fetched.json()["document_number"] == "44125896"


def test_hu04_desactiva_y_reactiva(api: TestClient) -> None:
    client_id = api.post("/v1/clients", json=FAMILIA_QUISPE).json()["id"]

    assert api.post(f"/v1/clients/{client_id}/deactivate").json()["active"] is False
    assert api.get("/v1/clients").json() == []
    assert api.post(f"/v1/clients/{client_id}/activate").json()["active"] is True


def test_hu04_cliente_inexistente_responde_404(api: TestClient) -> None:
    response = api.get(f"/v1/clients/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "client.not_found"
