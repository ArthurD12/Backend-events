"""Compras de punta a punta con PostgreSQL real (017: HU27–HU29). Necesita Docker.

Recibir una compra sube el stock y deja entradas con costo, proveedor y compra, en la misma
transacción; recibir dos veces falla; la base impide cambiar una compra recibida.
"""

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from testcontainers.community.postgres import PostgresContainer

from local_eventos.main import create_app
from local_eventos.shared.infrastructure.db import create_engine
from tests.integration.auth import create_test_admin, sign_in, use_test_jwt_secret

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="module")
def api(database_url: str) -> Iterator[TestClient]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DATABASE_URL", database_url)
        use_test_jwt_secret(patch)
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        create_test_admin(database_url)
        with TestClient(create_app()) as client:
            sign_in(client)
            yield client


def _product(api: TestClient, code: str, min_stock: str) -> dict[str, Any]:
    response = api.post(
        "/v1/inventory/products",
        json={"code": code, "name": f"Producto {code}", "category": "SUPPLIES", "unit": "KG",
              "kind": "CONSUMABLE", "min_stock": min_stock},
    )  # fmt: skip
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def test_hu29_recibir_sube_el_stock_con_entradas_de_la_compra(api: TestClient) -> None:
    sugar = _product(api, "AZU-01", "10")
    oil = _product(api, "ACE-01", "4")
    supplier = api.post(
        "/v1/purchasing/suppliers",
        json={"name": "Distribuidora Lima", "document_type": "RUC",
              "document_number": "20123456789", "phone": "987654321"},
    ).json()  # fmt: skip
    shortages = api.get("/v1/purchasing/shortages").json()
    purchase = api.post(
        "/v1/purchasing/purchases",
        json={"lines": [{"product_id": s["product_id"], "quantity": s["suggested_quantity"]}
                        for s in shortages]},
    ).json()  # fmt: skip
    url = f"/v1/purchasing/purchases/{purchase['id']}"
    api.post(
        f"{url}/order",
        json={"supplier_id": supplier["id"], "lines": [
            {"product_id": sugar["id"], "unit_cost_cents": 380},
            {"product_id": oil["id"], "unit_cost_cents": 1200}]},
    )  # fmt: skip
    body = {"lines": [
        {"product_id": sugar["id"], "received_quantity": "9.5", "lot": "L-9",
         "expires_on": "2027-02-01"},
        {"product_id": oil["id"], "received_quantity": "4"}],
        "invoice_number": "F001-55"}  # fmt: skip

    received = api.post(f"{url}/receive", json=body)
    again = api.post(f"{url}/receive", json=body)
    history = api.get(f"/v1/inventory/products/{sugar['id']}/movements").json()["items"]

    assert [s["code"] for s in shortages] == ["ACE-01", "AZU-01"]
    assert purchase["code"].startswith("COM-") and purchase["code"].endswith("-0001")
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "RECEIVED"
    assert received.json()["total_cents"] == 3610 + 4800
    assert (again.status_code, again.json()["code"]) == (409, "purchasing.invalid_transition")
    assert api.get(f"/v1/inventory/products/{sugar['id']}").json()["stock"] == "9.500"
    assert api.get(f"/v1/inventory/products/{oil['id']}").json()["avg_cost_cents"] == 1200
    assert len(history) == 1
    entry = history[0]
    assert (entry["kind"], entry["quantity"], entry["unit_cost_cents"]) == ("ENTRY", "9.500", 380)
    assert (entry["supplier_id"], entry["purchase_id"], entry["lot"]) == (
        supplier["id"], purchase["id"], "L-9"
    )  # fmt: skip


def test_ca29_3_la_base_no_deja_cambiar_una_compra_recibida(
    api: TestClient, database_url: str
) -> None:
    async def run() -> None:
        engine = create_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("UPDATE purchasing_purchases SET invoice_number = 'X'")
                )
        finally:
            await engine.dispose()

    with pytest.raises(DBAPIError, match="no se modifica"):
        asyncio.run(run())


def test_documento_repetido_lo_ataja_la_base(api: TestClient) -> None:
    response = api.post(
        "/v1/purchasing/suppliers",
        json={"name": "Otra", "document_type": "RUC", "document_number": "20123456789",
              "phone": "987654321"},
    )  # fmt: skip

    assert (response.status_code, response.json()["code"]) == (409, "purchasing.document_taken")
