"""El navegador deja que el frontend (otra dirección) llame a la API solo si la API lo autoriza."""

from fastapi.testclient import TestClient

from local_eventos.main import create_app


async def _no_database() -> None:
    return None


def _preflight(origin: str) -> str | None:
    with TestClient(create_app(readiness_check=_no_database)) as client:
        response = client.options(
            "/v1/clients",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )
    return response.headers.get("access-control-allow-origin")


def test_el_frontend_en_desarrollo_puede_llamar_a_la_api() -> None:
    assert _preflight("http://localhost:3000") == "http://localhost:3000"


def test_otra_pagina_web_no_puede_llamar_a_la_api() -> None:
    assert _preflight("https://pagina-desconocida.com") is None
