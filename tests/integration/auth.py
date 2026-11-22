"""Ayudas de sesión para las pruebas de punta a punta con PostgreSQL real.

Crean un administrador con el mismo comando de la instalación (`just create-admin`) e inician
sesión por la API, igual que lo hará el frontend.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from local_eventos.modules.identity import composition
from local_eventos.shared.infrastructure.db import create_engine
from local_eventos.tools.create_admin import create_admin

TEST_JWT_SECRET = "clave-solo-para-pruebas-de-integracion"
ADMIN_EMAIL = "admin@darze.pe"
ADMIN_PASSWORD = "admin-clave-segura"


def use_test_jwt_secret(patch: pytest.MonkeyPatch) -> None:
    patch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    composition.token_issuer.cache_clear()


def create_test_admin(database_url: str) -> None:
    async def run() -> None:
        engine = create_engine(database_url)
        try:
            await create_admin(
                async_sessionmaker(engine, expire_on_commit=False),
                name="Administrador Darze",
                email=ADMIN_EMAIL,
                password=ADMIN_PASSWORD,
            )
        finally:
            await engine.dispose()

    asyncio.run(run())


def auth_headers(
    client: TestClient, email: str = ADMIN_EMAIL, password: str = ADMIN_PASSWORD
) -> dict[str, str]:
    """Inicia sesión por la API y devuelve la cabecera con el access token."""
    response = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def sign_in(client: TestClient, email: str = ADMIN_EMAIL, password: str = ADMIN_PASSWORD) -> None:
    """Inicia sesión y deja el token en las cabeceras de todas las peticiones del cliente."""
    client.headers.update(auth_headers(client, email, password))
