"""Ficha del evento de punta a punta (HU14): commercial, ledger, inventory e identity en una
petición, con PostgreSQL real. Necesita Docker: `uv run pytest -m integration`.
"""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from testcontainers.community.postgres import PostgresContainer

from local_eventos.main import create_app
from local_eventos.modules.commercial.infrastructure.clock import LimaClock
from tests.integration.auth import auth_headers, create_test_admin, sign_in, use_test_jwt_secret

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


def _event(api: TestClient) -> tuple[str, str]:
    client_id = api.post(
        "/v1/clients",
        json={"name": "José Ramírez", "document_type": "DNI", "document_number": "40000001",
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
            "guests": 120,
            "lines": [{"kind": "EXTRA", "description": "Paquete boda",
                       "unit_price_cents": 1_000_000}],
        },
    ).json()  # fmt: skip
    api.post(f"/v1/quotes/{quote['id']}/status", json={"status": "ACCEPTED"})
    contract_id: str = api.post("/v1/contracts", json={"quote_id": quote["id"]}).json()["id"]
    signed = api.post(
        f"/v1/contracts/{contract_id}/sign",
        json={"signed_on": TODAY.isoformat(), "signer_name": "José Ramírez",
              "advance": {"paid_on": TODAY.isoformat(), "method": "CASH"}},
    )  # fmt: skip
    assert signed.status_code == 200, signed.text
    event = api.post("/v1/events", json={"contract_id": contract_id})
    assert event.status_code == 201, event.text
    return event.json()["id"], contract_id


def test_hu14_ficha_con_pago_salida_de_material_y_actividad(api: TestClient) -> None:
    event_id, contract_id = _event(api)
    paid = api.post(
        f"/v1/contracts/{contract_id}/payments",
        json={"amount_cents": 100_000, "paid_on": TODAY.isoformat(), "method": "TRANSFER"},
    )
    product_id = api.post(
        "/v1/inventory/products",
        json={"code": "pla-01", "name": "Plato llano", "category": "DINNERWARE", "unit": "UNIT",
              "kind": "REUSABLE", "min_stock": "0"},
    ).json()["id"]  # fmt: skip
    api.post(
        "/v1/inventory/movements/entry",
        json={"product_id": product_id, "quantity": "200", "unit_cost_cents": 500},
    )
    exit_ = api.post(
        "/v1/inventory/movements/exit",
        json={"product_id": product_id, "event_id": event_id, "quantity": "120"},
    )
    api.post(f"/v1/events/{event_id}/activities", json={"description": "Probar menú"})
    api.post(f"/v1/events/{event_id}/notes", json={"text": "Faltan 20 copas"})
    api.post(
        "/v1/users",
        json={"name": "Compras Darze", "email": "compras@darze.pe", "password": "compras-clave-1",
              "role": "PURCHASING_MANAGER"},
    )  # fmt: skip
    purchasing = auth_headers(api, "compras@darze.pe", "compras-clave-1")
    api.post(
        "/v1/users",
        json={"name": "Ventas Darze", "email": "ventas@darze.pe", "password": "ventas-clave-1",
              "role": "EVENTS_MANAGER"},
    )  # fmt: skip
    sales = auth_headers(api, "ventas@darze.pe", "ventas-clave-1")
    worker = api.post(
        "/v1/staff",
        json={"name": "Rosa Quispe", "document_type": "DNI", "document_number": "12345678",
              "phone": "987654321", "function": "WAITER", "rate_cents": 4500},
    )  # fmt: skip
    assigned = api.post(
        "/v1/staff/assignments",
        json={"event_id": event_id, "worker_id": worker.json()["id"],
              "date": (TODAY + timedelta(days=40)).isoformat(), "start_time": "19:00:00",
              "end_time": "23:00:00", "pay_cents": 8000},
    )  # fmt: skip

    sheet = api.get(f"/v1/reports/events/{event_id}/sheet")
    without_account = api.get(f"/v1/reports/events/{event_id}/sheet", headers=purchasing)
    as_sales = api.get(f"/v1/reports/events/{event_id}/sheet", headers=sales)
    sales_staff_routes = [
        api.get("/v1/staff", headers=sales),
        api.get("/v1/staff/assignments", params={"event_id": event_id}, headers=sales),
    ]

    assert paid.status_code == 201, paid.text
    assert exit_.status_code == 201, exit_.text
    assert sheet.status_code == 200, sheet.text
    body = sheet.json()
    assert (body["event"]["venue"], body["event"]["coordinator_name"]) == (
        "Local Los Jardines",
        "Administrador Darze",
    )
    assert (body["client"]["name"], body["client"]["document_number"]) == (
        "José Ramírez",
        "40000001",
    )
    assert [(s["description"], s["quantity"]) for s in body["services"]] == [("Paquete boda", 1)]
    assert worker.status_code == 201, worker.text
    assert assigned.status_code == 201, assigned.text
    # 025: personal designado visible, nunca el pago, documento, teléfono ni tarifa.
    assert [(w["name"], w["role"], w["function"]) for w in body["staff"]] == [
        ("Rosa Quispe", "Mozo", "WAITER")
    ]
    for leaked in ("pay_cents", "document_number", "phone", "rate_cents", "8000", "12345678"):
        assert leaked not in str(body["staff"])
    assert as_sales.status_code == 200, as_sales.text
    assert as_sales.json()["staff"] == body["staff"]
    assert [r.status_code for r in sales_staff_routes] == [403, 403]
    assert without_account.json()["staff"] is None
    assert [(m["code"], m["out"], m["pending_return"]) for m in body["materials"]] == [
        ("PLA-01", "120.000", "120.000")
    ]
    account = body["account"]
    assert [p["kind"] for p in account["payments"]] == ["ADVANCE", "INSTALLMENT"]
    assert account["paid_cents"] == account["payments"][0]["amount_cents"] + 100_000
    assert account["balance_cents"] == 1_000_000 - account["paid_cents"]
    assert [a["description"] for a in body["follow_up"]["pending"]] == ["Probar menú"]
    assert [n["text"] for n in body["follow_up"]["recent_notes"]] == ["Faltan 20 copas"]
    assert without_account.status_code == 200, without_account.text
    assert without_account.json()["account"] is None
    assert without_account.json()["materials"] == body["materials"]
