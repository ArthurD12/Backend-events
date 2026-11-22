"""Panel del administrador de punta a punta con PostgreSQL real (HU31). Necesita Docker."""

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


def test_ca31_panel_con_datos_reales_de_la_base(api: TestClient) -> None:
    client_id = api.post(
        "/v1/clients",
        json={
            "name": "José Ramírez",
            "document_type": "DNI",
            "document_number": "44125896",
            "phone": "987654321",
        },
    ).json()["id"]
    today = LimaClock().today()

    def quote(days: int, amount: int) -> str:
        response = api.post(
            "/v1/quotes",
            json={
                "client_id": client_id,
                "event_type": "BIRTHDAY",
                "event_date": (today + timedelta(days=days)).isoformat(),
                "start_time": "15:00",
                "end_time": "20:00",
                "venue": "SJL",
                "guests": 50,
                "lines": [{"kind": "EXTRA", "description": "Servicio", "unit_price_cents": amount}],
            },
        )
        assert response.status_code == 201, response.text
        quote_id: str = response.json()["id"]
        return quote_id

    accepted = quote(10, 300_000)
    sent = quote(40, 100_000)
    quote(5, 50_000)
    api.post(f"/v1/quotes/{accepted}/status", json={"status": "ACCEPTED"})
    api.post(f"/v1/quotes/{sent}/status", json={"status": "SENT"})

    body = api.get("/v1/dashboard").json()
    quotes = body["quotes"]

    assert body["month"] == f"{today.year:04d}-{today.month:02d}"
    assert (quotes["drafts"], quotes["sent_pending"]) == (1, 1)
    assert (quotes["created_in_month"], quotes["accepted_in_month"]) == (3, 1)
    assert quotes["accepted_amount_cents"] == 300_000
    assert [q["id"] for q in quotes["upcoming"]] == [accepted]
    assert len(quotes["recent"]) == 3
    assert (
        api.get("/v1/dashboard", params={"month": "2020-01"}).json()["quotes"]["created_in_month"]
        == 0
    )
