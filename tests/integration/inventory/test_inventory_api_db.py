"""API de inventario de punta a punta: HTTP → caso de uso → PostgreSQL real (017).

Necesita Docker: `uv run pytest -m integration`.
"""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

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


def test_hu23_producto_entrada_merma_y_ajuste_con_su_historial(api: TestClient) -> None:
    product = api.post(
        "/v1/inventory/products",
        json={"code": "azu-01", "name": "Azúcar rubia", "category": "SUPPLIES", "unit": "KG",
              "kind": "CONSUMABLE", "min_stock": "5"},
    )  # fmt: skip
    product_id = product.json()["id"]

    entry = api.post(
        "/v1/inventory/movements/entry",
        json={"product_id": product_id, "quantity": "20.5", "unit_cost_cents": 380,
              "lot": "L-7", "expires_on": "2027-03-01"},
    )  # fmt: skip
    waste = api.post(
        "/v1/inventory/movements/waste",
        json={"product_id": product_id, "quantity": "0.5", "reason": "Se humedeció"},
    )
    too_much = api.post(
        "/v1/inventory/movements/adjustment",
        json={"product_id": product_id, "quantity": "-21", "reason": "conteo"},
    )
    found = api.get("/v1/inventory/products", params={"text": "AZUCAR"})
    history = api.get(f"/v1/inventory/products/{product_id}/movements")

    assert product.status_code == 201 and product.json()["code"] == "AZU-01"
    assert entry.status_code == 201 and entry.json()["stock"] == "20.500"
    assert waste.json()["stock"] == "20.000"
    assert (too_much.status_code, too_much.json()["code"]) == (409, "inventory.insufficient_stock")
    assert [(p["stock"], p["avg_cost_cents"]) for p in found.json()] == [("20.000", 380)]
    assert [m["kind"] for m in history.json()["items"]] == ["WASTE", "ENTRY"]


def test_hu26_evento_inexistente_se_consulta_en_commercial(api: TestClient) -> None:
    response = api.get(f"/v1/inventory/events/{uuid4()}/materials")

    assert (response.status_code, response.json()["code"]) == (404, "inventory.event_not_found")
