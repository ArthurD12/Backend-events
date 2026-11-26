"""Reportes y panel de punta a punta (020) con PostgreSQL real: evento con pagos, movimientos
de caja y almacén, y una compra. El JSON y el CSV tienen las mismas filas (CA-34.2).
Necesita Docker: `uv run pytest -m integration`.
"""

import csv
from collections.abc import Iterator
from datetime import timedelta
from io import StringIO
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
RANGE = {"from": (TODAY - timedelta(days=30)).isoformat(), "to": TODAY.isoformat()}


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


def _ok(response):  # type: ignore[no-untyped-def]
    assert response.status_code in (200, 201), response.text
    return response.json()


@pytest.fixture(scope="module")
def scenario(api: TestClient) -> dict[str, str]:
    client_id = _ok(api.post(
        "/v1/clients",
        json={"name": "José Ramírez", "document_type": "DNI", "document_number": "40000001",
              "phone": "987654321"},
    ))["id"]  # fmt: skip
    quote = _ok(api.post(
        "/v1/quotes",
        json={
            "client_id": client_id, "event_type": "WEDDING",
            "event_date": (TODAY + timedelta(days=5)).isoformat(),
            "start_time": "20:00", "end_time": "23:00", "venue": "Local", "guests": 120,
            "lines": [{"kind": "EXTRA", "description": "Paquete", "unit_price_cents": 1_000_000}],
        },
    ))  # fmt: skip
    _ok(api.post(f"/v1/quotes/{quote['id']}/status", json={"status": "ACCEPTED"}))
    contract_id = _ok(api.post("/v1/contracts", json={"quote_id": quote["id"]}))["id"]
    _ok(api.post(
        f"/v1/contracts/{contract_id}/sign",
        json={"signed_on": TODAY.isoformat(), "signer_name": "José Ramírez",
              "advance": {"paid_on": TODAY.isoformat(), "method": "CASH"}},
    ))  # fmt: skip
    event_id = _ok(api.post("/v1/events", json={"contract_id": contract_id}))["id"]
    installment = _ok(api.post(
        f"/v1/contracts/{contract_id}/payments",
        json={"amount_cents": 100_000, "paid_on": TODAY.isoformat(), "method": "TRANSFER"},
    ))  # fmt: skip
    voided = _ok(api.post(
        f"/v1/contracts/{contract_id}/payments",
        json={"amount_cents": 50_000, "paid_on": TODAY.isoformat(), "method": "CASH"},
    ))["payment"]  # fmt: skip
    _ok(api.post(f"/v1/payments/{voided['id']}/void", json={"reason": "Duplicado"}))
    _ok(api.post(
        "/v1/movements",
        json={"type": "EXPENSE", "category": "STAFF", "concept": "Mozos", "amount_cents": 80_000,
              "method": "CASH", "occurred_on": TODAY.isoformat(), "event_id": event_id},
    ))  # fmt: skip
    product_id = _ok(api.post(
        "/v1/inventory/products",
        json={"code": "lec-01", "name": "Leche", "category": "BEVERAGES", "unit": "LITER",
              "kind": "CONSUMABLE", "min_stock": "50"},
    ))["id"]  # fmt: skip
    _ok(api.post(
        "/v1/inventory/movements/entry",
        json={"product_id": product_id, "quantity": "20", "unit_cost_cents": 350,
              "expires_on": (TODAY + timedelta(days=3)).isoformat()},
    ))  # fmt: skip
    _ok(api.post(
        "/v1/inventory/movements/exit",
        json={"product_id": product_id, "event_id": event_id, "quantity": "5"},
    ))  # fmt: skip
    supplier_id = _ok(api.post(
        "/v1/purchasing/suppliers",
        json={"name": "Distribuidora Lima", "document_type": "RUC",
              "document_number": "20123456789", "phone": "987654321"},
    ))["id"]  # fmt: skip
    purchase = _ok(api.post(
        "/v1/purchasing/purchases",
        json={"lines": [{"product_id": product_id, "quantity": "10"}], "event_id": event_id},
    ))  # fmt: skip
    _ok(api.post(
        f"/v1/purchasing/purchases/{purchase['id']}/order",
        json={"supplier_id": supplier_id,
              "lines": [{"product_id": product_id, "unit_cost_cents": 400}]},
    ))  # fmt: skip
    _ok(api.post(
        "/v1/purchasing/purchases",
        json={"lines": [{"product_id": product_id, "quantity": "3"}]},
    ))  # fmt: skip
    return {"event_id": event_id, "installment": installment["payment"]["number"]}


def _csv(api: TestClient, path: str, params: dict[str, str]) -> list[list[str]]:
    response = api.get(path, params={**params, "format": "csv"})
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"\xef\xbb\xbf")
    return list(csv.reader(StringIO(response.content.decode("utf-8-sig")), delimiter=";"))


def test_ca32_1_eventos_con_saldo_y_mismas_filas_en_csv(
    api: TestClient, scenario: dict[str, str]
) -> None:
    params = {"from": TODAY.isoformat(), "to": (TODAY + timedelta(days=30)).isoformat()}
    body = _ok(api.get("/v1/reports/events", params=params))
    rows = _csv(api, "/v1/reports/events", params)

    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert (row["client"], row["status"], row["total"]) == ("José Ramírez", "Programado", 1_000_000)
    assert row["paid"] == 600_000 and row["balance"] == 400_000  # adelanto 50 % + 100 000
    assert rows[1][0] == row["code"] and rows[1][-1] == "4000,00"
    assert len(rows) == 1 + len(body["rows"]) + 1 + len(body["totals"])


def test_ca32_2_caja_con_anulado_marcado(api: TestClient, scenario: dict[str, str]) -> None:
    body = _ok(api.get("/v1/reports/cash", params=RANGE))
    rows = _csv(api, "/v1/reports/cash", RANGE)

    assert [(r["type"], r["voided"]) for r in body["rows"]] == [
        ("Pago de cliente", False), ("Pago de cliente", False), ("Pago de cliente", True),
        ("Egreso", False),
    ]  # fmt: skip
    assert len({r["event"] for r in body["rows"]}) == 1  # pagos y egreso del mismo evento
    assert body["rows"][0]["event"].startswith("EVT-")
    totals = {t["key"]: t["value"] for t in body["totals"]}
    assert (totals["client_payments"], totals["expenses"], totals["net"]) == (
        600_000, 80_000, 520_000
    )  # fmt: skip
    assert [r[3] for r in rows[1:5]] == [r["concept"] for r in body["rows"]]
    assert f"Pago parcial {scenario['installment']}" in [r["concept"] for r in body["rows"]]


def test_ca32_3_y_ca32_4_almacen_y_compras(api: TestClient, scenario: dict[str, str]) -> None:
    stock = _ok(api.get("/v1/reports/inventory"))
    moves = _ok(api.get("/v1/reports/inventory-movements", params=RANGE))
    purchases = _ok(api.get("/v1/reports/purchases", params=RANGE))
    ordered = _ok(api.get("/v1/reports/purchases", params={**RANGE, "status": "ORDERED"}))
    pdf = api.get("/v1/reports/purchases", params={**RANGE, "format": "pdf"})

    assert stock["rows"][0]["stock"] == "15.000" and stock["rows"][0]["low_stock"] is True
    assert stock["rows"][0]["expiring_soon"] is True
    assert [(m["kind"], m["event"] is not None) for m in moves["rows"]] == [
        ("Entrada", False), ("Salida", True)
    ]  # fmt: skip
    assert [(p["status"], p["total"]) for p in purchases["rows"]] == [
        ("Ordenada", 4_000), ("Solicitada", None)
    ]  # fmt: skip
    assert purchases["rows"][0]["supplier"] == "Distribuidora Lima"
    assert len(ordered["rows"]) == 1
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_permisos_y_personal(api: TestClient, scenario: dict[str, str]) -> None:
    _ok(api.post(
        "/v1/users",
        json={"name": "Compras Darze", "email": "compras2@darze.pe",
              "password": "compras-clave-1", "role": "PURCHASING_MANAGER"},
    ))  # fmt: skip
    purchasing = auth_headers(api, "compras2@darze.pe", "compras-clave-1")
    params = {"from": TODAY.isoformat(), "to": (TODAY + timedelta(days=30)).isoformat()}

    events = api.get("/v1/reports/events", params=params, headers=purchasing)
    cash = api.get("/v1/reports/cash", params=RANGE, headers=purchasing)
    staff = api.get("/v1/reports/staff")

    assert events.status_code == 200 and events.json()["rows"][0]["total"] is None
    assert cash.status_code == 403
    assert (staff.status_code, staff.json()["code"]) == (503, "report.unavailable")


def test_ca31_panel_ampliado(api: TestClient, scenario: dict[str, str]) -> None:
    body = _ok(api.get("/v1/dashboard"))

    assert [e["id"] for e in body["upcoming_events"]] == [scenario["event_id"]]
    assert body["upcoming_events"][0]["balance_cents"] == 400_000
    assert body["receivables"]["total_cents"] == 400_000
    assert body["receivables"]["overdue_contracts"] == 1  # vence 7 días antes del evento
    assert body["inventory"] == {"low_stock": 1, "expiring_soon": 1}
    assert body["purchases"] == {"requested": 1, "ordered": 1, "open": 2}
    assert body["cash"]["expense_cents"] == 80_000  # caja del mes actual
    assert body["cash"]["income_cents"] == 600_000
