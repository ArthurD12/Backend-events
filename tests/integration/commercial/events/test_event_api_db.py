"""Evento de punta a punta: cotización → contrato → firma → evento, con PostgreSQL real (HU10).

HTTP → casos de uso → `commercial` e `identity` (responsables) → PostgreSQL. Necesita Docker.
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


def _signed_contract(api: TestClient, document: str) -> str:
    client_id = api.post(
        "/v1/clients",
        json={"name": "José Ramírez", "document_type": "DNI", "document_number": document,
              "phone": "987654321"},
    ).json()["id"]  # fmt: skip
    quote = api.post(
        "/v1/quotes",
        json={
            "client_id": client_id,
            "event_type": "QUINCEANERA",
            "event_date": (TODAY + timedelta(days=40)).isoformat(),
            "start_time": "21:00",
            "end_time": "04:00",
            "venue": "Local Los Jardines",
            "guests": 150,
            "lines": [
                {"kind": "EXTRA", "description": "Paquete quince", "unit_price_cents": 800_000},
                {"kind": "EXTRA", "description": "Movilidad", "unit_price_cents": 15_000},
            ],
        },
    ).json()
    api.post(f"/v1/quotes/{quote['id']}/status", json={"status": "ACCEPTED"})
    contract_id: str = api.post("/v1/contracts", json={"quote_id": quote["id"]}).json()["id"]
    api.post(
        f"/v1/contracts/{contract_id}/sign",
        json={
            "signed_on": TODAY.isoformat(),
            "signer_name": "José Ramírez",
            "advance": {"paid_on": TODAY.isoformat(), "method": "CASH"},
        },
    )
    return contract_id


def test_ca10_flujo_completo_en_la_base(api: TestClient) -> None:
    contract_id = _signed_contract(api, "40000001")
    coordinators = api.get("/v1/events/coordinators").json()

    response = api.post("/v1/events", json={"contract_id": contract_id})
    event = response.json()
    contract = api.get(f"/v1/contracts/{contract_id}").json()
    listed = api.get("/v1/events", params={"text": event["code"]}).json()
    cancel = api.post(f"/v1/contracts/{contract_id}/cancel", json={"reason": "Canceló"})

    assert [c["name"] for c in coordinators] == ["Administrador Darze"]
    assert response.status_code == 201, response.text
    assert event["code"] == f"EVT-{TODAY.year}-0001"
    assert event["status"] == "SCHEDULED"
    assert (event["coordinator_id"], event["coordinator_name"]) == (
        coordinators[0]["id"],
        "Administrador Darze",
    )
    assert (event["guests"], event["ends_next_day"]) == (150, True)
    assert [s["description"] for s in event["services"]] == ["Paquete quince", "Movilidad"]
    assert contract["event_id"] == event["id"]
    assert [e["id"] for e in listed["items"]] == [event["id"]]
    assert (cancel.status_code, cancel.json()["code"]) == (409, "contract.has_event")
    assert api.get(f"/v1/events/{event['id']}").json() == event


def test_ca10_5_no_se_convierte_dos_veces(api: TestClient) -> None:
    contract_id = _signed_contract(api, "40000002")
    api.post("/v1/events", json={"contract_id": contract_id})

    again = api.post("/v1/events", json={"contract_id": contract_id})

    assert (again.status_code, again.json()["code"]) == (409, "event.already_exists")
