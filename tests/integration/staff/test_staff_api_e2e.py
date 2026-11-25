"""API de personal de punta a punta: HTTP → caso de uso → PostgreSQL real (HU15, T-18).

Necesita Docker. Cubre el ciclo completo de un trabajador (alta, listado, consulta,
edición, baja y reactivación) con sesión de administrador, que `/ready` sigue en verde
y que sin sesión la API responde 401.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from testcontainers.community.postgres import PostgresContainer

from local_eventos.main import create_app
from tests.integration.auth import create_test_admin, sign_in, use_test_jwt_secret

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]

_WORKER = {
    "name": "Rosa Quispe",
    "document_type": "DNI",
    "document_number": "12345678",
    "phone": "987654321",
    "function": "COOK",
    "worker_type": "FIXED",
    "rate_cents": 4500,
    "overtime_applies": False,
}


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
            yield client


def test_e2e_ciclo_completo_de_un_trabajador(api: TestClient) -> None:
    sign_in(api)

    created = api.post("/v1/staff", json=_WORKER)
    assert created.status_code == 201, created.text
    worker = created.json()
    worker_id = worker["id"]
    assert worker["status"] == "ACTIVE"
    assert worker["currency"] == "PEN"

    listed = api.get("/v1/staff", params={"text": "Rosa"})
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [worker_id]

    fetched = api.get(f"/v1/staff/{worker_id}")
    assert fetched.status_code == 200
    assert fetched.json()["document_number"] == "12345678"

    updated = api.put(
        f"/v1/staff/{worker_id}",
        json={**_WORKER, "name": "Rosa Quispe Ríos", "rate_cents": 5000},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Rosa Quispe Ríos"
    assert updated.json()["rate_cents"] == 5000

    deactivated = api.post(f"/v1/staff/{worker_id}/deactivate", json={"reason": "Fin de temporada"})
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["status"] == "INACTIVE"

    activated = api.post(f"/v1/staff/{worker_id}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "ACTIVE"


def test_ready_sigue_en_verde(api: TestClient) -> None:
    assert api.get("/ready").status_code == 200


def test_sin_sesion_responde_401() -> None:
    with TestClient(create_app()) as anonymous:
        assert anonymous.get("/v1/staff").status_code == 401
