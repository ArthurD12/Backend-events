"""Cotizaciones de punta a punta: HTTP → caso de uso → catálogo → PostgreSQL real.

Necesita Docker: `just test-all`.
"""

from collections.abc import Iterator
from datetime import date, timedelta
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

ROOT = Path(__file__).resolve().parents[4]
EVENT_DATE = (LimaClock().today() + timedelta(days=30)).isoformat()


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


@pytest.fixture(scope="module")
def setup(api: TestClient) -> dict[str, str]:
    client = api.post(
        "/v1/clients",
        json={
            "name": "José Ramírez",
            "document_type": "DNI",
            "document_number": "44125896",
            "phone": "987654321",
        },
    ).json()
    category = api.post("/v1/catalog/categories", json={"name": "Buffets"}).json()
    service = api.post(
        "/v1/catalog/services",
        json={
            "name": "Buffet criollo",
            "category_id": category["id"],
            "price_unit": "PER_PERSON",
            "reference_price_cents": 4500,
        },
    ).json()
    return {"client": client["id"], "service": service["id"], "category": category["id"]}


def _body(setup: dict[str, str], **changes: Any) -> dict[str, Any]:
    return {
        "client_id": setup["client"],
        "event_type": "BIRTHDAY",
        "event_date": EVENT_DATE,
        "start_time": "15:00",
        "end_time": "20:00",
        "venue": "Calle Las Flores 123, SJL",
        "guests": 50,
        "lines": [
            {"kind": "SERVICE", "service_id": setup["service"]},
            {"kind": "EXTRA", "description": "Movilidad", "unit_price_cents": 8000},
        ],
        **changes,
    }


def test_ca07_crea_cotizacion_con_servicio_del_catalogo(
    api: TestClient, setup: dict[str, str]
) -> None:
    response = api.post("/v1/quotes", json=_body(setup))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"] == f"COT-{LimaClock().today().year}-0001"
    assert body["lines"][0]["description"] == "Buffet criollo"
    assert body["lines"][0]["quantity"] == 50
    assert body["total_cents"] == 50 * 4500 + 8000


def test_regla_6_cambiar_el_precio_del_catalogo_no_altera_la_cotizacion(
    api: TestClient, setup: dict[str, str]
) -> None:
    quote = api.post("/v1/quotes", json=_body(setup)).json()
    api.put(
        f"/v1/catalog/services/{setup['service']}",
        json={
            "name": "Buffet criollo",
            "category_id": setup["category"],
            "price_unit": "PER_PERSON",
            "reference_price_cents": 9900,
        },
    )

    after = api.get(f"/v1/quotes/{quote['id']}").json()
    edited = api.put(f"/v1/quotes/{quote['id']}", json=_body(setup, guests=60)).json()
    new_quote = api.post("/v1/quotes", json=_body(setup)).json()

    assert after["lines"][0]["unit_price_cents"] == 4500
    assert edited["lines"][0]["catalog_price_cents"] == 4500  # congelado al editar
    assert edited["lines"][0]["quantity"] == 60
    assert new_quote["lines"][0]["unit_price_cents"] == 9900  # la nueva usa el precio nuevo


def test_ca08_flujo_de_estados_y_busqueda_en_la_base(
    api: TestClient, setup: dict[str, str]
) -> None:
    quote = api.post("/v1/quotes", json=_body(setup)).json()
    url = f"/v1/quotes/{quote['id']}"

    api.post(f"{url}/status", json={"status": "SENT"})
    accepted = api.post(f"{url}/status", json={"status": "ACCEPTED"})
    locked = api.put(url, json=_body(setup))
    found = api.get("/v1/quotes", params={"text": "jose ramirez", "status": "ACCEPTED"}).json()

    assert accepted.json()["status"] == "ACCEPTED"
    assert locked.status_code == 409
    assert [item["code"] for item in found["items"]] == [quote["code"]]


def test_ca08_5_filtra_por_fecha_del_evento(api: TestClient, setup: dict[str, str]) -> None:
    day = date.fromisoformat(EVENT_DATE)

    inside = api.get(
        "/v1/quotes", params={"event_date_from": EVENT_DATE, "event_date_to": EVENT_DATE}
    ).json()
    outside = api.get(
        "/v1/quotes", params={"event_date_from": (day + timedelta(days=1)).isoformat()}
    ).json()

    assert inside["total"] >= 3
    assert outside["total"] == 0
