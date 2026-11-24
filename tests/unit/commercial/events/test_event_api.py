"""API de eventos (HU10) con piezas en memoria. Sin base de datos."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.commercial.domain.clients.client import Client, DocumentType
from local_eventos.modules.commercial.presentation import dependencies as deps
from local_eventos.modules.identity.domain.permissions import Role, permissions_of
from local_eventos.modules.identity.public_api import (
    Coordinator,
    CurrentUser,
    get_current_user,
)
from local_eventos.modules.ledger.application.use_cases.payments import (
    ContractPayments,
    RecordPayment,
)
from tests.unit.commercial.clients.fakes import InMemoryClientRepository
from tests.unit.commercial.contracts.fakes import InMemoryContractRepository
from tests.unit.commercial.quotes.fakes import (
    FakeClock,
    FakeServiceLookup,
    InMemoryQuoteRepository,
)
from tests.unit.current_user import signed_in_as
from tests.unit.ledger.fakes import InMemoryPaymentRepository

from .fakes import FakeCoordinators, InMemoryEventRepository


async def _no_database() -> None:
    return None


@dataclass
class Api:
    client: TestClient
    me: Coordinator
    other: Coordinator

    def contract(self, *, signed: bool = True) -> str:
        quote = self.client.post(
            "/v1/quotes",
            json={
                "client_id": self.customer_id,
                "event_type": "BIRTHDAY",
                "event_date": "2026-12-19",
                "start_time": "20:00",
                "end_time": "02:00",
                "venue": "Local Los Jardines",
                "guests": 80,
                "lines": [
                    {"kind": "EXTRA", "description": "Paquete fiesta", "unit_price_cents": 500_000},
                    {"kind": "EXTRA", "description": "Movilidad", "unit_price_cents": 15_000},
                ],
            },
        ).json()
        self.client.post(f"/v1/quotes/{quote['id']}/status", json={"status": "ACCEPTED"})
        contract_id: str = self.client.post("/v1/contracts", json={"quote_id": quote["id"]}).json()[
            "id"
        ]
        if signed:
            self.client.post(
                f"/v1/contracts/{contract_id}/sign",
                json={
                    "signed_on": "2026-11-22",
                    "signer_name": "José Ramírez",
                    "advance": {"paid_on": "2026-11-22", "method": "CASH"},
                },
            )
        return contract_id

    def convert(self, contract_id: str, **changes: Any) -> Any:
        return self.client.post("/v1/events", json={"contract_id": contract_id, **changes})

    def sign_in_as(self, role: Role) -> None:
        self.client.app.dependency_overrides[get_current_user] = signed_in_as(role)  # type: ignore[attr-defined]

    customer_id: str = ""

    @staticmethod
    def customer_id_unknown() -> str:
        return "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def api() -> Iterator[Api]:
    clients = InMemoryClientRepository()
    customer = Client.register(
        name="José Ramírez", document_type=DocumentType.DNI, document_number="44125896",
        phone="987654321",
    )  # fmt: skip
    clients.clients[customer.id] = customer
    names = {customer.id: customer.name}
    quotes = InMemoryQuoteRepository(names)
    contracts = InMemoryContractRepository(names)
    events = InMemoryEventRepository(names)
    payments = InMemoryPaymentRepository()
    clock = FakeClock()
    user = CurrentUser(
        id=uuid4(), name="Rosa Huamán", role=Role.EVENTS_MANAGER,
        permissions=permissions_of(Role.EVENTS_MANAGER),
    )  # fmt: skip

    async def current() -> CurrentUser:
        return user

    me = Coordinator(id=user.id, name=user.name)
    other = Coordinator(id=customer.id, name="Harold Canaza")  # cualquier id distinto sirve
    coordinators = FakeCoordinators(me, other)

    def dep(value: object) -> Any:
        async def dependency() -> object:
            return value

        return dependency

    app = create_app(readiness_check=_no_database)
    app.dependency_overrides.update(
        {
            deps.get_quote_repository: dep(quotes),
            deps.get_client_repository: dep(clients),
            deps.get_contract_repository: dep(contracts),
            deps.get_event_repository: dep(events),
            deps.get_coordinator_lookup: dep(coordinators),
            deps.get_service_lookup: dep(FakeServiceLookup()),
            deps.get_payment_recorder: dep(RecordPayment(payments)),
            deps.get_payments_lookup: dep(ContractPayments(payments)),
            deps.get_clock: lambda: clock,
            get_current_user: current,
        }
    )
    with TestClient(app) as client:
        yield Api(client, me, other, customer_id=str(customer.id))


def test_ca10_convierte_y_relaciona_contrato_y_evento(api: Api) -> None:
    contract_id = api.contract()

    response = api.convert(contract_id)
    contract = api.client.get(f"/v1/contracts/{contract_id}").json()

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == "EVT-2026-0001"
    assert body["status"] == "SCHEDULED"
    assert (body["contract_code"], body["quote_code"]) == ("CON-2026-0001", "COT-2026-0001")
    assert body["client_name"] == "José Ramírez"
    assert (body["event_date"], body["start_time"], body["end_time"]) == (
        "2026-12-19",
        "20:00:00",
        "02:00:00",
    )
    assert body["ends_next_day"] is True
    assert (body["venue"], body["guests"]) == ("Local Los Jardines", 80)
    assert (body["coordinator_id"], body["coordinator_name"]) == (str(api.me.id), api.me.name)
    assert [(s["description"], s["quantity"]) for s in body["services"]] == [
        ("Paquete fiesta", 1),
        ("Movilidad", 1),
    ]
    assert contract["event_id"] == body["id"]
    assert api.client.get(f"/v1/events/{body['id']}").json() == body


def test_ca10_errores_al_convertir(api: Api) -> None:
    signed = api.contract()
    api.convert(signed)

    twice = api.convert(signed)
    pending = api.convert(api.contract(signed=False))
    bad_coordinator = api.convert(api.contract(), coordinator_id=api.customer_id_unknown())
    missing = api.convert("00000000-0000-0000-0000-000000000000")

    assert (twice.status_code, twice.json()["code"]) == (409, "event.already_exists")
    assert (pending.status_code, pending.json()["code"]) == (409, "event.contract_not_ready")
    assert (bad_coordinator.status_code, bad_coordinator.json()["code"]) == (
        422,
        "event.coordinator_invalid",
    )
    assert (missing.status_code, missing.json()["code"]) == (404, "contract.not_found")


def test_r_evt_3_contrato_con_evento_no_se_anula(api: Api) -> None:
    contract_id = api.contract()
    api.convert(contract_id)

    response = api.client.post(f"/v1/contracts/{contract_id}/cancel", json={"reason": "Canceló"})

    assert (response.status_code, response.json()["code"]) == (409, "contract.has_event")


def test_lista_y_responsables(api: Api) -> None:
    api.convert(api.contract(), coordinator_id=str(api.other.id))
    api.convert(api.contract())

    page = api.client.get("/v1/events", params={"text": "ramirez", "page_size": 1}).json()
    january = api.client.get("/v1/events", params={"date_from": "2027-01-01"}).json()
    coordinators = api.client.get("/v1/events/coordinators").json()

    assert (page["total"], len(page["items"])) == (2, 1)
    assert page["items"][0]["coordinator_name"] == "Harold Canaza"
    assert january["total"] == 0
    assert [c["name"] for c in coordinators] == [api.me.name, "Harold Canaza"]


def test_permisos_compras_lee_pero_no_convierte(api: Api) -> None:
    contract_id = api.contract()
    api.sign_in_as(Role.PURCHASING_MANAGER)

    listed = api.client.get("/v1/events")
    converted = api.convert(contract_id)
    coordinators = api.client.get("/v1/events/coordinators")

    assert listed.status_code == 200
    assert (converted.status_code, converted.json()["code"]) == (403, "auth.forbidden")
    assert coordinators.status_code == 403


def test_ca11_cancelar_evento_por_api(api: Api) -> None:
    contract_id = api.contract()
    event_id = api.convert(contract_id).json()["id"]
    url = f"/v1/events/{event_id}/cancel"

    no_reason = api.client.post(url, json={"reason": " "})
    cancelled = api.client.post(
        url,
        json={
            "reason": "El cliente canceló",
            "refund_cents": 100_000,
            "refund": {"paid_on": "2026-11-22", "method": "CASH"},
            "note": "Se devolvió en efectivo",
        },
    )
    again = api.client.post(url, json={"reason": "Otra vez"})
    contract = api.client.get(f"/v1/contracts/{contract_id}").json()
    listed = api.client.get("/v1/events", params={"status": "CANCELLED"}).json()

    assert (no_reason.status_code, no_reason.json()["code"]) == (422, "event.reason_required")
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["status"] == "CANCELLED"
    assert body["cancellation"]["reason"] == "El cliente canceló"
    assert (body["cancellation"]["refund_cents"], body["cancellation"]["note"]) == (
        100_000,
        "Se devolvió en efectivo",
    )
    assert (again.status_code, again.json()["code"]) == (409, "event.not_cancellable")
    assert contract["status"] == "CANCELLED"
    assert [p["kind"] for p in contract["payments"]] == ["ADVANCE", "REFUND"]
    assert [e["id"] for e in listed["items"]] == [event_id]


def test_compras_no_cancela(api: Api) -> None:
    event_id = api.convert(api.contract()).json()["id"]
    api.sign_in_as(Role.PURCHASING_MANAGER)

    response = api.client.post(f"/v1/events/{event_id}/cancel", json={"reason": "x"})

    assert (response.status_code, response.json()["code"]) == (403, "auth.forbidden")


def test_ca12_calendario_por_api(api: Api) -> None:
    api.convert(api.contract())
    params = {"date_from": "2026-12-01", "date_to": "2026-12-31"}

    december = api.client.get("/v1/events/calendar", params=params)
    birthdays = api.client.get("/v1/events/calendar", params={**params, "event_type": "BIRTHDAY"})
    weddings = api.client.get("/v1/events/calendar", params={**params, "event_type": "WEDDING"})
    too_long = api.client.get(
        "/v1/events/calendar", params={"date_from": "2026-01-01", "date_to": "2026-12-31"}
    )
    missing = api.client.get("/v1/events/calendar", params={"date_from": "2026-12-01"})
    api.sign_in_as(Role.PURCHASING_MANAGER)
    purchasing = api.client.get("/v1/events/calendar", params=params)

    assert december.status_code == 200
    (item,) = december.json()
    assert (item["event_date"], item["start_time"], item["client_name"]) == (
        "2026-12-19",
        "20:00:00",
        "José Ramírez",
    )
    assert (item["event_type"], item["status"], item["coordinator_name"]) == (
        "BIRTHDAY",
        "SCHEDULED",
        api.me.name,
    )
    assert len(birthdays.json()) == 1 and weddings.json() == []
    assert (too_long.status_code, too_long.json()["code"]) == (422, "event.range_invalid")
    assert missing.status_code == 422
    assert purchasing.status_code == 200
