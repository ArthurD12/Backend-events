"""API del historial del cliente (HU05) con piezas en memoria. Sin base de datos."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.commercial.domain.clients.client import Client, DocumentType
from local_eventos.modules.commercial.presentation import dependencies as deps
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from tests.unit.commercial.clients.fakes import InMemoryClientRepository
from tests.unit.commercial.contracts.fakes import InMemoryContractRepository
from tests.unit.commercial.events.fakes import InMemoryEventRepository
from tests.unit.commercial.quotes.fakes import FakeClock, InMemoryQuoteRepository
from tests.unit.current_user import signed_in_as


async def _no_database() -> None:
    return None


def _dep(value: object) -> Any:
    async def dependency() -> object:
        return value

    return dependency


@pytest.fixture
def api() -> Iterator[tuple[TestClient, Client]]:
    clients = InMemoryClientRepository()
    customer = Client.register(
        name="José Ramírez", document_type=DocumentType.DNI, document_number="44125896",
        phone="987654321",
    )  # fmt: skip
    clients.clients[customer.id] = customer
    clock = FakeClock()
    app = create_app(readiness_check=_no_database)
    app.dependency_overrides.update(
        {
            deps.get_client_repository: _dep(clients),
            deps.get_quote_repository: _dep(InMemoryQuoteRepository()),
            deps.get_contract_repository: _dep(InMemoryContractRepository()),
            deps.get_event_repository: _dep(InMemoryEventRepository()),
            deps.get_clock: lambda: clock,
            get_current_user: signed_in_as(Role.EVENTS_MANAGER),
        }
    )
    with TestClient(app) as client:
        yield client, customer


def test_ca05_historial_por_api(api: tuple[TestClient, Client]) -> None:
    client, customer = api

    response = client.get(f"/v1/clients/{customer.id}/history")

    assert response.status_code == 200
    body = response.json()
    assert body["client"]["name"] == "José Ramírez"
    assert body["summary"] == {
        "quotes": 0,
        "accepted_quotes": 0,
        "events": 0,
        "contracted_cents": 0,
    }
    assert (body["quotes"], body["events"]) == ([], [])


def test_ca05_cliente_inexistente(api: tuple[TestClient, Client]) -> None:
    client, _ = api

    response = client.get("/v1/clients/00000000-0000-0000-0000-000000000000/history")

    assert (response.status_code, response.json()["code"]) == (404, "client.not_found")


def test_ca05_4_compras_no_ve_el_historial(api: tuple[TestClient, Client]) -> None:
    client, customer = api
    client.app.dependency_overrides[get_current_user] = signed_in_as(Role.PURCHASING_MANAGER)  # type: ignore[attr-defined]

    response = client.get(f"/v1/clients/{customer.id}/history")

    assert (response.status_code, response.json()["code"]) == (403, "auth.forbidden")
