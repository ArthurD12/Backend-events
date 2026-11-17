"""API de clientes de punta a punta: HTTP → caso de uso → PostgreSQL real (HU04).

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

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[4]

COLEGIO = {
    "name": "Colegio San Martín",
    "document_type": "RUC",
    "document_number": "20125478963",
    "phone": "01-654-3210",
}


@pytest.fixture(scope="module")
def api() -> Iterator[TestClient]:
    with (
        PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres,
        pytest.MonkeyPatch.context() as patch,
    ):
        patch.setenv("DATABASE_URL", postgres.get_connection_url())
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        with TestClient(create_app()) as client:
            yield client


def test_hu04_registra_y_encuentra_el_cliente_en_la_base_de_datos(api: TestClient) -> None:
    created = api.post("/v1/clients", json=COLEGIO)

    found = api.get("/v1/clients", params={"text": "san martin"})

    assert created.status_code == 201
    assert [c["id"] for c in found.json()] == [created.json()["id"]]
    assert api.get("/ready").json() == {"status": "ready"}


def test_hu04_documento_duplicado_no_guarda_nada(api: TestClient) -> None:
    response = api.post("/v1/clients", json={**COLEGIO, "name": "Otro colegio"})

    assert response.status_code == 409
    assert response.json()["code"] == "client.document_duplicated"
    assert [c["name"] for c in api.get("/v1/clients").json()] == ["Colegio San Martín"]
