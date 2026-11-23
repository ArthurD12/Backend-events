"""Sesión, usuarios e historial de punta a punta: HTTP → caso de uso → PostgreSQL real.

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
from tests.integration.auth import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    auth_headers,
    create_test_admin,
    sign_in,
    use_test_jwt_secret,
)

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


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


def test_ca03_1_el_intento_fallido_queda_guardado_aunque_se_responda_401(
    api: TestClient,
) -> None:
    rejected = api.post("/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "equivocada"})
    sign_in(api)

    log = api.get("/v1/access-log").json()

    assert rejected.status_code == 401
    assert [item["result"] for item in log["items"]] == ["SUCCESS", "INVALID_CREDENTIALS"]
    assert log["items"][0]["user_name"] == "Administrador Darze"


def test_ca02_y_ca01_crea_usuario_que_entra_con_su_rol(api: TestClient) -> None:
    created = api.post(
        "/v1/users",
        json={
            "name": "Rosa Huamán",
            "email": "rosa@darze.pe",
            "password": "rosa-clave-segura",
            "role": "PURCHASING_MANAGER",
        },
    )
    rosa = auth_headers(api, "rosa@darze.pe", "rosa-clave-segura")

    assert created.status_code == 201
    assert api.get("/v1/auth/me", headers=rosa).json()["permissions"] == [
        "catalog:read",
        "events:read",
    ]
    assert api.get("/v1/catalog/services", headers=rosa).status_code == 200
    assert api.get("/v1/clients", headers=rosa).status_code == 403
    assert api.get("/v1/access-log", headers=rosa).status_code == 403


def test_ca02_4_al_desactivarlo_pierde_el_acceso_al_instante(api: TestClient) -> None:
    rosa = auth_headers(api, "rosa@darze.pe", "rosa-clave-segura")
    rosa_id = api.get("/v1/auth/me", headers=rosa).json()["id"]

    api.post(f"/v1/users/{rosa_id}/deactivate")

    assert api.get("/v1/auth/me", headers=rosa).status_code == 401
    retry = api.post(
        "/v1/auth/login", json={"email": "rosa@darze.pe", "password": "rosa-clave-segura"}
    )
    assert retry.status_code == 401


def test_ca01_5_refresh_rota_y_logout_cierra(api: TestClient) -> None:
    login = api.post("/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    first = login.json()["refresh_token"]

    renewed = api.post("/v1/auth/refresh", json={"refresh_token": first})
    reused = api.post("/v1/auth/refresh", json={"refresh_token": first})
    api.post("/v1/auth/logout", json={"refresh_token": renewed.json()["refresh_token"]})
    after_logout = api.post(
        "/v1/auth/refresh", json={"refresh_token": renewed.json()["refresh_token"]}
    )

    assert renewed.status_code == 200
    assert reused.status_code == 401
    assert after_logout.status_code == 401
