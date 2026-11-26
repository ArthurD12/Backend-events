"""Asistente de punta a punta con PostgreSQL real: las herramientas leen los `public_api` de
commercial, ledger e inventory. El modelo es `FakeLanguageModel` (nunca se llama al proveedor).

Necesita Docker: `uv run pytest -m integration`.
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from testcontainers.community.postgres import PostgresContainer

from local_eventos.main import create_app
from local_eventos.modules.assistant.application.ports.language_model import ToolCall
from local_eventos.modules.assistant.infrastructure.fake_language_model import (
    FakeLanguageModel,
    calls,
    says,
)
from local_eventos.modules.assistant.presentation import dependencies as deps
from tests.integration.auth import auth_headers, create_test_admin, sign_in, use_test_jwt_secret
from tests.integration.reporting.test_event_sheet_api_db import _event

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def api() -> Iterator[TestClient]:
    with (
        PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres,
        pytest.MonkeyPatch.context() as patch,
    ):
        url = postgres.get_connection_url()
        patch.setenv("DATABASE_URL", url)
        patch.setenv("ANTHROPIC_API_KEY", "")
        use_test_jwt_secret(patch)
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        create_test_admin(url)
        with TestClient(create_app()) as client:
            sign_in(client)
            yield client
            client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


def _use(api: TestClient, model: FakeLanguageModel | None) -> None:
    api.app.dependency_overrides[deps.get_language_model] = lambda: model  # type: ignore[attr-defined]


def test_without_key_the_assistant_is_unavailable_and_the_rest_works(api: TestClient) -> None:
    assert api.get("/v1/assistant/status").json() == {"available": False}
    response = api.post("/v1/assistant/ask", json={"question": "hola"})
    assert response.status_code == 503 and response.json()["code"] == "assistant.unavailable"
    assert api.get("/v1/clients").status_code == 200


def test_tools_read_real_data_with_the_user_permissions(api: TestClient) -> None:
    event_id, _ = _event(api)
    code = api.get(f"/v1/events/{event_id}").json()["code"]
    model = FakeLanguageModel(
        [
            calls(
                ToolCall("a", "event_account", {"code": code}),
                ToolCall("b", "pending_collections", {}),
                ToolCall("c", "event_detail", {"code": code}),
                ToolCall("d", "upcoming_events", {"days": 90}),
                ToolCall("e", "search_clients", {"name": "Ramírez"}),
                ToolCall("f", "stock_alerts", {}),
                ToolCall("g", "open_purchases", {}),
                ToolCall("h", "cash_flow", {}),
                ToolCall("i", "event_requirement", {"code": code}),
            ),
            says("Listo"),
        ]
    )
    _use(api, model)

    response = api.post("/v1/assistant/ask", json={"question": "¿cómo va el evento?"})

    assert response.status_code == 200, response.text
    assert [t["error"] for t in response.json()["tools"]] == [False] * 9
    results = {r.call_id: json.loads(r.content) for r in model.calls[1][-1].tool_results}
    assert results["a"]["evento"] == code and results["a"]["pagado"].startswith("S/ ")
    assert results["b"]["eventos"][0]["codigo"] == code
    assert results["c"]["cliente"] == "José Ramírez" and results["c"]["responsable"]
    assert results["d"]["total"] >= 1
    assert results["e"]["clientes"][0]["nombre"] == "José Ramírez"

    log = api.get("/v1/assistant/log").json()
    assert log["total"] >= 1 and log["items"][0]["tools"][0]["input"] == {"code": code}
    assert log["items"][0]["user_name"] == "Administrador Darze"


def test_purchasing_manager_cannot_read_money_tools(api: TestClient) -> None:
    api.post(
        "/v1/users",
        json={"name": "Compras Darze", "email": "compras@darze.pe", "password": "compras-clave-1",
              "role": "PURCHASING_MANAGER"},
    )  # fmt: skip
    purchasing = auth_headers(api, "compras@darze.pe", "compras-clave-1")
    model = FakeLanguageModel(
        [calls(ToolCall("a", "pending_collections", {}), ToolCall("b", "stock_alerts", {})),
         says("No tienes permiso")]
    )  # fmt: skip
    _use(api, model)

    response = api.post("/v1/assistant/ask", json={"question": "cobros"}, headers=purchasing)

    assert response.json()["tools"] == [
        {"name": "pending_collections", "input": {}, "error": True},
        {"name": "stock_alerts", "input": {}, "error": False},
    ]
    assert api.get("/v1/assistant/log", headers=purchasing).status_code == 403
