"""API de sesión, usuarios e historial (HU01–HU03) con piezas en memoria. Sin base de datos."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.domain.user import User
from local_eventos.modules.identity.presentation import dependencies as deps

from .fakes import (
    FakeClock,
    FakePasswordHasher,
    FakeTokenIssuer,
    InMemoryAccessLogRepository,
    InMemorySessionRepository,
    InMemoryUserRepository,
)

ADMIN_PASSWORD = "admin-clave-segura"


async def _no_database() -> None:
    return None


@dataclass
class Api:
    client: TestClient
    users: InMemoryUserRepository
    log: InMemoryAccessLogRepository
    clock: FakeClock

    def login(self, email: str = "admin@darze.pe", password: str = ADMIN_PASSWORD) -> Any:
        return self.client.post("/v1/auth/login", json={"email": email, "password": password})

    def headers(
        self, email: str = "admin@darze.pe", password: str = ADMIN_PASSWORD
    ) -> dict[str, str]:
        token = self.login(email, password).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def api() -> Iterator[Api]:
    users = InMemoryUserRepository()
    sessions = InMemorySessionRepository()
    log = InMemoryAccessLogRepository(users)
    clock = FakeClock()
    hasher = FakePasswordHasher()
    tokens = FakeTokenIssuer(clock)
    admin = User.create(
        name="Administrador Darze",
        email="admin@darze.pe",
        password_hash=hasher.hash(ADMIN_PASSWORD),
        role=Role.ADMIN,
    )
    users.users[admin.id] = admin

    async def users_dep() -> InMemoryUserRepository:
        return users

    async def sessions_dep() -> InMemorySessionRepository:
        return sessions

    async def log_dep() -> InMemoryAccessLogRepository:
        return log

    app = create_app(readiness_check=_no_database)
    app.dependency_overrides.update(
        {
            deps.get_user_repository: users_dep,
            deps.get_session_repository: sessions_dep,
            deps.get_access_log_repository: log_dep,
            deps.get_password_hasher: lambda: hasher,
            deps.get_token_issuer: lambda: tokens,
            deps.get_clock: lambda: clock,
        }
    )
    with TestClient(app) as client:
        yield Api(client, users, log, clock)


def _new_user(api: Api, **changes: Any) -> Any:
    body = {
        "name": "Luis Quispe",
        "email": "luis@darze.pe",
        "password": "luis-clave-segura",
        "role": "EVENTS_MANAGER",
        **changes,
    }
    return api.client.post("/v1/users", json=body, headers=api.headers())


def test_ca01_1_login_entrega_tokens_y_permisos(api: Api) -> None:
    response = api.login()

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    assert body["refresh_token"]
    assert body["user"]["role"] == "ADMIN"
    assert "users:manage" in body["user"]["permissions"]


def test_ca01_2_credenciales_incorrectas_responden_401_sin_revelar_el_motivo(api: Api) -> None:
    wrong_password = api.login(password="equivocada")
    unknown_email = api.login(email="nadie@darze.pe")

    for response in (wrong_password, unknown_email):
        assert response.status_code == 401
        assert response.json()["code"] == "auth.invalid_credentials"
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]
    assert [a.result.value for a in api.log.attempts] == ["INVALID_CREDENTIALS"] * 2


def test_ca01_3_y_ca02_4_usuario_desactivado_no_entra(api: Api) -> None:
    luis_id = _new_user(api).json()["id"]
    api.client.post(f"/v1/users/{luis_id}/deactivate", headers=api.headers())

    response = api.login("luis@darze.pe", "luis-clave-segura")

    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_credentials"
    assert api.log.attempts[-1].result.value == "INACTIVE_USER"


def test_ca01_4_me_devuelve_solo_los_permisos_del_rol(api: Api) -> None:
    _new_user(api, role="PURCHASING_MANAGER")

    me = api.client.get("/v1/auth/me", headers=api.headers("luis@darze.pe", "luis-clave-segura"))

    assert me.status_code == 200
    assert me.json()["permissions"] == ["catalog:read", "event_notes:write", "events:read"]


def test_ca01_5_logout_impide_renovar(api: Api) -> None:
    refresh_token = api.login().json()["refresh_token"]

    logout = api.client.post("/v1/auth/logout", json={"refresh_token": refresh_token})
    refresh = api.client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert logout.status_code == 204
    assert refresh.status_code == 401
    assert refresh.json()["code"] == "auth.session_expired"


def test_ca01_6_renueva_con_actividad_y_vence_sin_ella(api: Api) -> None:
    refresh_token = api.login().json()["refresh_token"]

    api.clock.advance(minutes=20)
    renewed = api.client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    api.clock.advance(minutes=30)
    expired = api.client.post(
        "/v1/auth/refresh", json={"refresh_token": renewed.json()["refresh_token"]}
    )

    assert renewed.status_code == 200
    assert expired.status_code == 401


def test_ca01_7_sin_token_401_y_sin_permiso_403(api: Api) -> None:
    _new_user(api, role="EVENTS_MANAGER")

    anonymous = api.client.get("/v1/users")
    forbidden = api.client.get(
        "/v1/users", headers=api.headers("luis@darze.pe", "luis-clave-segura")
    )

    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "auth.not_authenticated"
    assert anonymous.headers["www-authenticate"] == "Bearer"
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "auth.forbidden"


def test_ca02_1_crea_usuario_sin_devolver_la_clave(api: Api) -> None:
    response = _new_user(api)

    assert response.status_code == 201
    assert response.json()["email"] == "luis@darze.pe"
    assert "password" not in response.text
    assert "hash" not in response.text


def test_ca02_2_correo_repetido_responde_409(api: Api) -> None:
    _new_user(api)

    response = _new_user(api, email="LUIS@darze.pe")

    assert response.status_code == 409
    assert response.json()["code"] == "user.email_duplicated"


def test_r_id_1_clave_corta_responde_422(api: Api) -> None:
    response = _new_user(api, password="corta")

    assert response.status_code == 422
    assert response.json()["code"] == "user.password_too_short"


def test_ca02_3_modifica_datos_rol_y_clave(api: Api) -> None:
    luis_id = _new_user(api).json()["id"]

    response = api.client.put(
        f"/v1/users/{luis_id}",
        json={
            "name": "Luis A. Quispe",
            "email": "luis@darze.pe",
            "role": "PURCHASING_MANAGER",
            "new_password": "nueva-clave-segura",
        },
        headers=api.headers(),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "PURCHASING_MANAGER"
    assert api.login("luis@darze.pe", "nueva-clave-segura").status_code == 200
    assert api.login("luis@darze.pe", "luis-clave-segura").status_code == 401


def test_ca02_5_desactivado_sigue_en_la_lista_completa(api: Api) -> None:
    luis_id = _new_user(api).json()["id"]
    headers = api.headers()
    api.client.post(f"/v1/users/{luis_id}/deactivate", headers=headers)

    active = api.client.get("/v1/users", headers=headers).json()
    everyone = api.client.get("/v1/users", params={"include_inactive": True}, headers=headers)

    assert [u["email"] for u in active] == ["admin@darze.pe"]
    assert len(everyone.json()) == 2
    assert api.client.get(f"/v1/users/{luis_id}", headers=headers).json()["active"] is False


def test_r_id_4_no_desactiva_al_ultimo_admin(api: Api) -> None:
    admin_id = next(iter(api.users.users))

    response = api.client.post(f"/v1/users/{admin_id}/deactivate", headers=api.headers())

    assert response.status_code == 409
    assert response.json()["code"] == "user.last_admin"


def test_ca03_2_y_ca03_3_solo_el_admin_ve_el_historial_filtrado(api: Api) -> None:
    _new_user(api)
    api.login(password="equivocada")
    headers = api.headers()

    failed = api.client.get(
        "/v1/access-log", params={"result": "INVALID_CREDENTIALS"}, headers=headers
    )
    forbidden = api.client.get(
        "/v1/access-log", headers=api.headers("luis@darze.pe", "luis-clave-segura")
    )

    assert failed.status_code == 200
    body = failed.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "admin@darze.pe"
    assert body["items"][0]["user_name"] == "Administrador Darze"
    assert forbidden.status_code == 403


def test_ca03_4_no_hay_rutas_para_modificar_el_historial(api: Api) -> None:
    headers = api.headers()

    assert api.client.delete("/v1/access-log", headers=headers).status_code == 405
    assert api.client.put("/v1/access-log", headers=headers).status_code == 405
