"""API del catálogo de punta a punta: HTTP → caso de uso → PostgreSQL real (HU06).

Necesita Docker: `just test-all`.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from testcontainers.community.postgres import PostgresContainer

from local_eventos.main import create_app
from tests.integration.auth import create_test_admin, sign_in, use_test_jwt_secret

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def api() -> Iterator[TestClient]:
    with (
        PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres,
        pytest.MonkeyPatch.context() as patch,
    ):
        patch.setenv("DATABASE_URL", postgres.get_connection_url())
        use_test_jwt_secret(patch)
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        create_test_admin(postgres.get_connection_url())
        with TestClient(create_app()) as client:
            sign_in(client)
            yield client


def test_hu06_crea_categoria_y_servicio_y_los_encuentra(api: TestClient) -> None:
    category = api.post("/v1/catalog/categories", json={"name": "Buffets"})
    service = api.post(
        "/v1/catalog/services",
        json={
            "name": "Buffet criollo",
            "category_id": category.json()["id"],
            "price_unit": "PER_PERSON",
            "reference_price_cents": 4500,
        },
    )

    found = api.get("/v1/catalog/services", params={"text": "BUFFET"})

    assert category.status_code == 201
    assert service.status_code == 201
    assert [s["id"] for s in found.json()] == [service.json()["id"]]
    assert found.json()[0]["currency"] == "PEN"


def test_hu06_categoria_con_servicios_activos_no_se_desactiva_ni_cambia(api: TestClient) -> None:
    category_id = api.get("/v1/catalog/categories").json()[0]["id"]

    response = api.post(f"/v1/catalog/categories/{category_id}/deactivate")

    assert response.status_code == 409
    assert response.json()["code"] == "catalog.category_has_active_services"
    assert api.get("/v1/catalog/categories").json()[0]["active"] is True


def test_hu06_nombre_repetido_no_guarda_nada(api: TestClient) -> None:
    response = api.post("/v1/catalog/categories", json={"name": "buffets"})

    assert response.status_code == 409
    assert [c["name"] for c in api.get("/v1/catalog/categories").json()] == ["Buffets"]
