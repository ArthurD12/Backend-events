"""API de cotizaciones (HU07–HU08) con piezas en memoria. Sin base de datos."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.commercial.domain.clients.client import Client, DocumentType
from local_eventos.modules.commercial.presentation import dependencies as deps
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from tests.unit.commercial.clients.fakes import InMemoryClientRepository
from tests.unit.current_user import signed_in_as

from .fakes import FakeClock, FakeServiceLookup, InMemoryQuoteRepository


async def _no_database() -> None:
    return None


@dataclass
class Api:
    client: TestClient
    clock: FakeClock
    catalog: FakeServiceLookup
    customer: Client
    buffet: str
    chairs: str

    def body(self, **changes: Any) -> dict[str, Any]:
        return {
            "client_id": str(self.customer.id),
            "event_type": "WEDDING",
            "event_date": "2026-12-19",
            "start_time": "20:00",
            "end_time": "03:00",
            "venue": "Local Los Jardines",
            "guests": 100,
            "lines": [
                {"kind": "SERVICE", "service_id": self.buffet},
                {"kind": "SERVICE", "service_id": self.chairs, "quantity": 100},
                {"kind": "EXTRA", "description": "Movilidad", "unit_price_cents": 15000},
            ],
            **changes,
        }

    def create(self, **changes: Any) -> Any:
        return self.client.post("/v1/quotes", json=self.body(**changes))


@pytest.fixture
def api() -> Iterator[Api]:
    clients = InMemoryClientRepository()
    customer = Client.register(
        name="Familia Quispe",
        document_type=DocumentType.DNI,
        document_number="44125896",
        phone="987654321",
    )
    clients.clients[customer.id] = customer
    quotes = InMemoryQuoteRepository({customer.id: customer.name})
    catalog = FakeServiceLookup()
    buffet = catalog.add("Buffet criollo", "PER_PERSON", 4500)
    chairs = catalog.add("Silla Tiffany", "PER_UNIT", 650)
    clock = FakeClock()

    async def quotes_dep() -> InMemoryQuoteRepository:
        return quotes

    async def clients_dep() -> InMemoryClientRepository:
        return clients

    async def catalog_dep() -> FakeServiceLookup:
        return catalog

    app = create_app(readiness_check=_no_database)
    app.dependency_overrides.update(
        {
            deps.get_quote_repository: quotes_dep,
            deps.get_client_repository: clients_dep,
            deps.get_service_lookup: catalog_dep,
            deps.get_clock: lambda: clock,
            get_current_user: signed_in_as(Role.EVENTS_MANAGER),
        }
    )
    with TestClient(app) as client:
        yield Api(client, clock, catalog, customer, str(buffet), str(chairs))


def test_ca07_crea_borrador_con_codigo_total_y_lineas(api: Api) -> None:
    response = api.create()

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == "COT-2026-0001"
    assert body["status"] == "DRAFT"
    assert body["client_name"] == "Familia Quispe"
    assert body["ends_next_day"] is True
    assert body["valid_until"] == "2026-12-07"
    assert [line["subtotal_cents"] for line in body["lines"]] == [450_000, 65_000, 15_000]
    assert body["total_cents"] == 530_000
    assert body["currency"] == "PEN"


def test_ca07_5_el_total_del_frontend_se_ignora(api: Api) -> None:
    response = api.create(total_cents=1)

    assert response.json()["total_cents"] == 530_000


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"event_date": "2026-11-01"}, "quote.event_date_past"),
        ({"end_time": "20:00"}, "quote.time_invalid"),
        ({"guests": 0}, "quote.guests_invalid"),
        ({"lines": []}, "quote.lines_required"),
        ({"venue": " "}, "quote.venue_required"),
    ],
)
def test_datos_invalidos_responden_422_con_su_code(
    api: Api, changes: dict[str, Any], code: str
) -> None:
    response = api.create(**changes)

    assert response.status_code == 422
    assert response.json()["code"] == code


def test_ca07_1_y_regla_2_cliente_y_servicio_inactivos_responden_409(api: Api) -> None:
    api.catalog.change(UUID(api.chairs), active=False)
    service = api.create()
    api.customer.deactivate()
    client = api.create(lines=[{"kind": "SERVICE", "service_id": api.buffet}])

    assert (service.status_code, service.json()["code"]) == (409, "quote.service_inactive")
    assert (client.status_code, client.json()["code"]) == (409, "quote.client_inactive")


def test_ca08_flujo_editar_enviar_volver_a_borrador_y_aceptar(api: Api) -> None:
    quote_id = api.create().json()["id"]
    url = f"/v1/quotes/{quote_id}"

    edited = api.client.put(url, json=api.body(guests=120))
    sent = api.client.post(f"{url}/status", json={"status": "SENT"})
    blocked = api.client.put(url, json=api.body(guests=130))
    back = api.client.post(f"{url}/status", json={"status": "DRAFT"})
    accepted = api.client.post(f"{url}/status", json={"status": "ACCEPTED"})
    locked = api.client.put(url, json=api.body())
    again = api.client.post(f"{url}/status", json={"status": "DRAFT"})

    assert edited.json()["lines"][0]["quantity"] == 120
    assert sent.json()["status"] == "SENT"
    assert (blocked.status_code, blocked.json()["code"]) == (409, "quote.not_editable")
    assert back.json()["status"] == "DRAFT"
    assert accepted.json()["status"] == "ACCEPTED"
    assert locked.json()["code"] == "quote.not_editable"
    assert (again.status_code, again.json()["code"]) == (409, "quote.invalid_transition")
    assert api.client.get(url).json()["status"] == "ACCEPTED"


def test_ca08_3_vencida_se_muestra_y_no_cambia_de_estado(api: Api) -> None:
    quote_id = api.create(valid_until="2026-11-25").json()["id"]
    api.clock.advance(days=5)

    detail = api.client.get(f"/v1/quotes/{quote_id}").json()
    accept = api.client.post(f"/v1/quotes/{quote_id}/status", json={"status": "ACCEPTED"})
    listed = api.client.get("/v1/quotes", params={"status": "EXPIRED"}).json()

    assert detail["status"] == "EXPIRED"
    assert (accept.status_code, accept.json()["code"]) == (409, "quote.expired")
    assert [item["id"] for item in listed["items"]] == [quote_id]


def test_ca08_5_busca_y_pagina(api: Api) -> None:
    for _ in range(3):
        api.create()

    page = api.client.get("/v1/quotes", params={"text": "quispe", "page_size": 2}).json()
    by_code = api.client.get("/v1/quotes", params={"text": "COT-2026-0003"}).json()

    assert (page["total"], len(page["items"]), page["page_size"]) == (3, 2, 2)
    assert [item["code"] for item in by_code["items"]] == ["COT-2026-0003"]


def test_cotizacion_inexistente_responde_404(api: Api) -> None:
    response = api.client.get("/v1/quotes/00000000-0000-0000-0000-000000000000")

    assert (response.status_code, response.json()["code"]) == (404, "quote.not_found")


def test_permisos_compras_no_usa_cotizaciones_y_sin_sesion_401(api: Api) -> None:
    app = api.client.app
    app.dependency_overrides[get_current_user] = signed_in_as(Role.PURCHASING_MANAGER)  # type: ignore[attr-defined]
    forbidden = api.client.get("/v1/quotes")
    del app.dependency_overrides[get_current_user]  # type: ignore[attr-defined]
    anonymous = api.client.get("/v1/quotes")

    assert (forbidden.status_code, forbidden.json()["code"]) == (403, "auth.forbidden")
    assert anonymous.status_code == 401
