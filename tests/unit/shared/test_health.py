"""Pruebas de `/health`, `/ready` y del contrato OpenAPI (000-bootstrap). Sin base de datos."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import API_TITLE, API_VERSION, create_app


async def _database_down() -> None:
    raise ConnectionRefusedError("password authentication failed for user darze at 10.0.0.5")


async def _database_up() -> None:
    return None


@pytest.fixture
def client_without_db() -> Iterator[TestClient]:
    with TestClient(create_app(readiness_check=_database_down)) as client:
        yield client


def test_ca2_health_responde_sin_base_de_datos(client_without_db: TestClient) -> None:
    response = client_without_db.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ca4_ready_sin_base_de_datos_no_expone_detalles(client_without_db: TestClient) -> None:
    response = client_without_db.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert "password" not in response.text
    assert "10.0.0.5" not in response.text


def test_ca3_ready_cuando_la_base_de_datos_responde() -> None:
    with TestClient(create_app(readiness_check=_database_up)) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ca8_openapi_tiene_titulo_version_y_operation_ids(client_without_db: TestClient) -> None:
    spec = client_without_db.get("/openapi.json").json()

    assert spec["info"]["title"] == API_TITLE == "Darze API"
    assert spec["info"]["version"] == API_VERSION == "1.0.0"
    assert spec["paths"]["/health"]["get"]["operationId"] == "health_live"
    assert spec["paths"]["/ready"]["get"]["operationId"] == "health_ready"
