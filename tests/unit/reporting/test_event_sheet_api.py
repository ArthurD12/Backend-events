"""API de la ficha del evento (HU14): una petición, por bloques; pagos con `payments:record`."""

from collections.abc import Callable, Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.reporting.presentation import dependencies as deps
from tests.unit.current_user import signed_in_as

from .sheet_fakes import EVENT_ID, SheetFakes

URL = f"/v1/reports/events/{EVENT_ID}/sheet"


async def _no_database() -> None:
    return None


@pytest.fixture
def api_as() -> Iterator[Callable[[Role], TestClient]]:
    fakes = SheetFakes()
    app = create_app(readiness_check=_no_database)
    app.dependency_overrides.update(
        {
            deps.get_event_detail: lambda: fakes.details,
            deps.get_event_follow_up: lambda: fakes.follow_up,
            deps.get_event_materials: lambda: fakes.materials,
            deps.get_event_account: lambda: fakes.accounts,
            deps.get_event_staff: lambda: fakes.event_staff,
            deps.get_user_names: lambda: fakes.user_names,
        }
    )
    with TestClient(app) as client:

        def login(role: Role) -> TestClient:
            app.dependency_overrides[get_current_user] = signed_in_as(role)
            return client

        yield login


def test_ca14_ficha_por_bloques(api_as: Callable[[Role], TestClient]) -> None:
    response = api_as(Role.EVENTS_MANAGER).get(URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "event", "client", "services", "staff", "materials", "account", "follow_up",
    }  # fmt: skip
    assert (body["event"]["code"], body["event"]["coordinator_name"]) == (
        "EVT-2026-0001",
        "Rosa Huamán",
    )
    assert (body["client"]["document_number"], body["client"]["phone"]) == (
        "40000001",
        "987654321",
    )
    assert body["services"] == [
        {"kind": "SERVICE", "service_id": body["services"][0]["service_id"],
         "description": "Buffet criollo", "unit": "PER_PERSON", "quantity": 120}
    ]  # fmt: skip
    assert body["staff"] is None
    assert [(m["code"], m["out"], m["pending_return"]) for m in body["materials"]] == [
        ("PLA-01", "50.000", "4.000")
    ]
    assert body["account"]["balance_cents"] == 300_000
    assert [p["number"] for p in body["account"]["payments"]] == ["PAG-2026-0001"]
    follow_up = body["follow_up"]
    assert [a["description"] for a in follow_up["pending"]] == ["Confirmar mozos"]
    assert [a["description"] for a in follow_up["done"]] == ["Probar menú"]
    assert [(n["text"], n["created_by_name"]) for n in follow_up["recent_notes"]] == [
        ("Faltan 20 copas", "Harold Canaza")
    ]


def test_ca14_5_compras_ve_la_ficha_sin_pagos(api_as: Callable[[Role], TestClient]) -> None:
    response = api_as(Role.PURCHASING_MANAGER).get(URL)

    assert response.status_code == 200
    assert response.json()["account"] is None
    assert response.json()["materials"] != []


def test_evento_inexistente_404(api_as: Callable[[Role], TestClient]) -> None:
    response = api_as(Role.ADMIN).get(f"/v1/reports/events/{uuid4()}/sheet")

    assert (response.status_code, response.json()["code"]) == (404, "event.not_found")


def test_sin_sesion_401() -> None:
    with TestClient(create_app(readiness_check=_no_database)) as client:
        assert client.get(URL).status_code == 401
