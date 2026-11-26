"""Contrato de punta a punta: cotización → contrato → firma con adelanto → pago → anulación.

HTTP → casos de uso → `commercial` y `ledger` → PostgreSQL real (HU41–HU42). Necesita Docker.
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
from tests.integration.auth import create_test_admin, sign_in, use_test_jwt_secret

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[4]
TODAY = LimaClock().today()


@pytest.fixture(scope="module")
def env() -> Iterator[tuple[TestClient, str]]:
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
            yield client, url


def _accepted_quote(api: TestClient, document: str) -> str:
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
            "venue": "SJL",
            "guests": 100,
            "lines": [{"kind": "EXTRA", "description": "Paquete", "unit_price_cents": 500_000}],
        },
    ).json()
    api.post(f"/v1/quotes/{quote['id']}/status", json={"status": "ACCEPTED"})
    quote_id: str = quote["id"]
    return quote_id


def test_ca41_ca42_flujo_completo_en_la_base(env: tuple[TestClient, str]) -> None:
    api, _ = env
    quote_id = _accepted_quote(api, "40000001")

    contract = api.post("/v1/contracts", json={"quote_id": quote_id}).json()
    signed = api.post(
        f"/v1/contracts/{contract['id']}/sign",
        json={
            "signed_on": TODAY.isoformat(),
            "signer_name": "José Ramírez",
            "advance": {"paid_on": TODAY.isoformat(), "method": "TRANSFER", "reference": "Op 9"},
        },
    ).json()
    cancelled = api.post(
        f"/v1/contracts/{contract['id']}/cancel",
        json={"reason": "Canceló el evento", "refund_cents": 100_000},
    ).json()

    assert contract["code"] == f"CON-{TODAY.year}-0001"
    assert contract["advance_cents"] == 250_000
    assert signed["status"] == "SIGNED" and signed["can_become_event"] is True
    assert cancelled["status"] == "CANCELLED"
    assert [(p["kind"], p["amount_cents"]) for p in cancelled["payments"]] == [
        ("ADVANCE", 250_000),
        ("REFUND", 100_000),
    ]
    assert api.get(f"/v1/quotes/{quote_id}").json()["contract_id"] == contract["id"]


def test_r_con_5_una_cotizacion_un_solo_contrato(env: tuple[TestClient, str]) -> None:
    api, _ = env
    quote_id = _accepted_quote(api, "40000002")
    first = api.post("/v1/contracts", json={"quote_id": quote_id}).json()
    api.post(f"/v1/contracts/{first['id']}/cancel", json={"reason": "Error"})

    again = api.post("/v1/contracts", json={"quote_id": quote_id})

    assert (again.status_code, again.json()["code"]) == (409, "contract.already_exists")


def test_ca43_descarga_el_pdf_del_contrato_con_los_datos_de_la_base(
    env: tuple[TestClient, str],
) -> None:
    api, _ = env
    contract = api.post("/v1/contracts", json={"quote_id": _accepted_quote(api, "40000004")}).json()
    pending = api.get(f"/v1/contracts/{contract['id']}/pdf")
    api.post(
        f"/v1/contracts/{contract['id']}/sign",
        json={"signed_on": TODAY.isoformat(), "signer_name": "José Ramírez",
              "advance": {"paid_on": TODAY.isoformat(), "method": "CASH"}},
    )  # fmt: skip
    signed = api.get(f"/v1/contracts/{contract['id']}/pdf")
    api.post(f"/v1/contracts/{contract['id']}/cancel", json={"reason": "El cliente canceló"})
    cancelled = api.get(f"/v1/contracts/{contract['id']}/pdf")

    disposition = f'attachment; filename="{contract["code"]}.pdf"'
    for response in (pending, signed):
        assert response.status_code == 200
        assert response.headers["content-disposition"] == disposition
        assert response.content.startswith(b"%PDF")
    assert (cancelled.status_code, cancelled.json()["code"]) == (409, "contract.pdf_not_available")


def test_hu19_a_hu22_pagos_caja_y_reportes_en_la_base(env: tuple[TestClient, str]) -> None:
    api, _ = env
    contract = api.post("/v1/contracts", json={"quote_id": _accepted_quote(api, "40000003")}).json()
    api.post(
        f"/v1/contracts/{contract['id']}/sign",
        json={
            "signed_on": TODAY.isoformat(),
            "signer_name": "José Ramírez",
            "advance": {"paid_on": TODAY.isoformat(), "method": "CASH"},
        },
    )
    pay = {"paid_on": TODAY.isoformat(), "method": "TRANSFER", "reference": "Op 1"}
    first = api.post(
        f"/v1/contracts/{contract['id']}/payments", json={"amount_cents": 100_000, **pay}
    ).json()["payment"]
    api.post(f"/v1/payments/{first['id']}/void", json={"reason": "Voucher repetido"})
    api.post(f"/v1/contracts/{contract['id']}/payments", json={"amount_cents": 250_000, **pay})
    over = api.post(f"/v1/contracts/{contract['id']}/payments", json={"amount_cents": 1, **pay})
    account = api.get(f"/v1/contracts/{contract['id']}/account").json()
    receipt = api.get(f"/v1/payments/{first['id']}/receipt.pdf")
    coordinator = api.get("/v1/events/coordinators").json()[0]["id"]
    event = api.post(
        "/v1/events", json={"contract_id": contract["id"], "coordinator_id": coordinator}
    ).json()
    api.post(
        "/v1/movements",
        json={"type": "EXPENSE", "category": "STAFF", "concept": "Mozos", "amount_cents": 60_000,
              "method": "CASH", "occurred_on": TODAY.isoformat(), "event_id": event["id"]},
    )  # fmt: skip
    result = api.get(f"/v1/reports/events/{event['id']}/result").json()
    flow = api.get(
        "/v1/reports/cash-flow", params={"from": TODAY.isoformat(), "to": TODAY.isoformat()}
    ).json()

    assert first["number"].startswith(f"PAG-{TODAY.year}-")
    assert (over.status_code, over.json()["code"]) == (422, "payment.exceeds_balance")
    assert (account["paid_cents"], account["balance_cents"]) == (500_000, 0)
    assert [p["void"] is not None for p in account["payments"]] == [False, True, False]
    assert receipt.status_code == 200 and receipt.content.startswith(b"%PDF")
    assert (event["paid_cents"], event["balance_cents"]) == (500_000, 0)
    assert (result["collected_cents"], result["expense_cents"], result["result_cents"]) == (
        500_000,
        60_000,
        440_000,
    )
    assert flow["totals"]["expenses"]["staff_cents"] >= 60_000
