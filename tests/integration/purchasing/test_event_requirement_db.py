"""Recetas, requerimiento, reservas, compra desde faltantes y egreso de punta a punta (021).

PostgreSQL real; necesita Docker: `uv run pytest -m integration`.
"""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from testcontainers.community.postgres import PostgresContainer

from local_eventos.main import create_app
from local_eventos.modules.commercial.infrastructure.clock import LimaClock
from tests.integration.auth import create_test_admin, sign_in, use_test_jwt_secret

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
TODAY = LimaClock().today()


@pytest.fixture(scope="module")
def api() -> Iterator[TestClient]:
    with (
        PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres,
        pytest.MonkeyPatch.context() as patch,
    ):
        url = postgres.get_connection_url()
        patch.setenv("DATABASE_URL", url)
        use_test_jwt_secret(patch)
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        create_test_admin(url)
        with TestClient(create_app()) as client:
            sign_in(client)
            yield client


def _event(api: TestClient, service_id: str, document: str) -> str:
    client_id = api.post(
        "/v1/clients",
        json={"name": "José Ramírez", "document_type": "DNI", "document_number": document,
              "phone": "987654321"},
    ).json()["id"]  # fmt: skip
    quote = api.post(
        "/v1/quotes",
        json={
            "client_id": client_id,
            "event_type": "WEDDING",
            "event_date": (TODAY + timedelta(days=40)).isoformat(),
            "start_time": "20:00",
            "end_time": "03:00",
            "venue": "Local Los Jardines",
            "guests": 100,
            "lines": [{"kind": "SERVICE", "service_id": service_id}],
        },
    ).json()  # fmt: skip
    api.post(f"/v1/quotes/{quote['id']}/status", json={"status": "ACCEPTED"})
    contract_id = api.post("/v1/contracts", json={"quote_id": quote["id"]}).json()["id"]
    signed = api.post(
        f"/v1/contracts/{contract_id}/sign",
        json={"signed_on": TODAY.isoformat(), "signer_name": "José Ramírez",
              "advance": {"paid_on": TODAY.isoformat(), "method": "CASH"}},
    )  # fmt: skip
    assert signed.status_code == 200, signed.text
    event = api.post("/v1/events", json={"contract_id": contract_id})
    assert event.status_code == 201, event.text
    return str(event.json()["id"])


def _requirement(api: TestClient, event_id: str) -> dict[str, Any]:
    response = api.get(f"/v1/inventory/events/{event_id}/requirement")
    assert response.status_code == 200, response.text
    return response.json()


def test_021_receta_requerimiento_reserva_salida_compra_recepcion_y_egreso(
    api: TestClient,
) -> None:
    category = api.post("/v1/catalog/categories", json={"name": "Buffets"}).json()["id"]
    service_id = api.post(
        "/v1/catalog/services",
        json={"name": "Buffet criollo", "category_id": category, "price_unit": "PER_PERSON",
              "reference_price_cents": 4500},
    ).json()["id"]  # fmt: skip
    rice = api.post(
        "/v1/inventory/products",
        json={"code": "arr-01", "name": "Arroz", "category": "SUPPLIES", "unit": "KG",
              "kind": "CONSUMABLE", "min_stock": "0"},
    ).json()["id"]  # fmt: skip
    recipe = api.put(
        f"/v1/inventory/recipes/{service_id}",
        json={"lines": [{"product_id": rice, "quantity": "0.15", "basis": "PER_PERSON"}]},
    )
    event_id = _event(api, service_id, "40000011")

    first = _requirement(api, event_id)["lines"][0]
    api.post(
        "/v1/inventory/movements/entry",
        json={"product_id": rice, "quantity": "6", "unit_cost_cents": 400},
    )
    reserved = api.post(
        f"/v1/inventory/events/{event_id}/reservations",
        json={"lines": [{"product_id": rice, "quantity": "4"}]},
    )
    after_reserve = _requirement(api, event_id)["lines"][0]
    exit_ = api.post(
        "/v1/inventory/movements/exit",
        json={"product_id": rice, "event_id": event_id, "quantity": "3"},
    )
    after_exit = _requirement(api, event_id)["lines"][0]

    assert recipe.status_code == 200, recipe.text
    assert (first["required"], first["available"], first["shortage"]) == (
        "15.000", "0.000", "15.000",
    )  # fmt: skip
    assert reserved.status_code == 201, reserved.text
    assert (after_reserve["reserved"], after_reserve["available"], after_reserve["shortage"]) == (
        "4.000", "2.000", "9.000",
    )  # fmt: skip
    assert exit_.status_code == 201, exit_.text
    assert (after_exit["out"], after_exit["reserved"], after_exit["available"]) == (
        "3.000", "1.000", "2.000",
    )  # fmt: skip
    assert after_exit["shortage"] == "9.000"

    purchase = api.post(f"/v1/purchasing/purchases/from-event/{event_id}")
    assert purchase.status_code == 201, purchase.text
    assert purchase.json()["event_id"] == event_id
    assert purchase.json()["lines"][0]["quantity"] == "9.000"
    url = f"/v1/purchasing/purchases/{purchase.json()['id']}"
    supplier = api.post(
        "/v1/purchasing/suppliers",
        json={"name": "Distribuidora Lima", "document_type": "RUC",
              "document_number": "20123456789", "phone": "987654321"},
    ).json()  # fmt: skip
    api.post(
        f"{url}/order",
        json={"supplier_id": supplier["id"],
              "lines": [{"product_id": rice, "unit_cost_cents": 400}]},
    )  # fmt: skip
    too_early = api.post(f"{url}/expense", json={})
    received = api.post(
        f"{url}/receive",
        json={"lines": [{"product_id": rice, "received_quantity": "9"}],
              "invoice_number": "F001-77"},
    )  # fmt: skip
    covered = _requirement(api, event_id)["lines"][0]
    pdf = api.get(f"{url}/pdf")
    expense = api.post(f"{url}/expense", json={"method": "TRANSFER"})
    again = api.post(f"{url}/expense", json={})

    assert too_early.json()["code"] == "purchasing.expense_not_available"
    assert received.status_code == 200, received.text
    assert covered["shortage"] == "0.000"
    assert (pdf.status_code, pdf.headers["content-type"]) == (200, "application/pdf")
    assert pdf.content.startswith(b"%PDF")
    assert expense.status_code == 200, expense.text
    assert again.json()["code"] == "purchasing.expense_already_registered"
    movement_id = expense.json()["expense_movement_id"]
    movements = api.get("/v1/movements", params={"event_id": event_id}).json()
    listed = [m for m in movements["items"] if m["id"] == movement_id]
    assert [(m["type"], m["category"], m["amount_cents"]) for m in listed] == [
        ("EXPENSE", "SUPPLIES", 3600)
    ]

    cancelled = api.post(f"/v1/events/{event_id}/cancel", json={"reason": "El cliente desistió"})
    other = _event(api, service_id, "40000012")
    taken = api.post(
        f"/v1/inventory/events/{other}/reservations",
        json={"lines": [{"product_id": rice, "quantity": "12"}]},
    )  # todo el stock: solo es posible si la reserva del evento cancelado se liberó

    assert cancelled.status_code == 200, cancelled.text
    assert _requirement(api, event_id)["calculated"] is False
    assert taken.status_code == 201, taken.text
