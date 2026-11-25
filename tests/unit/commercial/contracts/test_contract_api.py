"""API de contratos (HU41–HU42) con piezas en memoria. Sin base de datos."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.commercial.application.quotes.ports.document import CompanyProfile
from local_eventos.modules.commercial.domain.clients.client import Client, DocumentType
from local_eventos.modules.commercial.presentation import dependencies as deps
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.ledger.application.use_cases.payments import (
    ContractPaymentEntries,
    FindPayment,
    RecordPayment,
    VoidPayment,
)
from tests.unit.commercial.clients.fakes import InMemoryClientRepository
from tests.unit.commercial.events.fakes import InMemoryEventRepository
from tests.unit.commercial.quotes.fakes import (
    FakeClock,
    FakeServiceLookup,
    InMemoryQuoteRepository,
)
from tests.unit.current_user import signed_in_as
from tests.unit.ledger.fakes import InMemoryPaymentRepository

from .fakes import InMemoryContractRepository


async def _no_database() -> None:
    return None


async def _names(user_ids: Any) -> dict[Any, str]:
    return {user_id: "Usuario de prueba" for user_id in user_ids}


@dataclass
class Api:
    client: TestClient
    payments: InMemoryPaymentRepository
    customer: Client

    def accepted_quote(self, amount: int = 545_000) -> str:
        quote = self.client.post(
            "/v1/quotes",
            json={
                "client_id": str(self.customer.id),
                "event_type": "WEDDING",
                "event_date": "2026-12-19",
                "start_time": "20:00",
                "end_time": "03:00",
                "venue": "SJL",
                "guests": 100,
                "lines": [{"kind": "EXTRA", "description": "Paquete", "unit_price_cents": amount}],
            },
        ).json()
        self.client.post(f"/v1/quotes/{quote['id']}/status", json={"status": "ACCEPTED"})
        quote_id: str = quote["id"]
        return quote_id

    def generate(self, quote_id: str, **changes: Any) -> Any:
        return self.client.post("/v1/contracts", json={"quote_id": quote_id, **changes})

    def sign(self, contract_id: str, **changes: Any) -> Any:
        body = {
            "signed_on": "2026-11-22",
            "signer_name": "José Ramírez",
            "advance": {"paid_on": "2026-11-22", "method": "YAPE_PLIN", "reference": "Op. 55"},
            **changes,
        }
        return self.client.post(f"/v1/contracts/{contract_id}/sign", json=body)


@pytest.fixture
def api() -> Iterator[Api]:
    clients = InMemoryClientRepository()
    customer = Client.register(
        name="José Ramírez", document_type=DocumentType.DNI, document_number="44125896",
        phone="987654321",
    )  # fmt: skip
    clients.clients[customer.id] = customer
    quotes = InMemoryQuoteRepository({customer.id: customer.name})
    contracts = InMemoryContractRepository({customer.id: customer.name})
    payments = InMemoryPaymentRepository()
    events = InMemoryEventRepository()
    clock = FakeClock()

    async def quotes_dep() -> InMemoryQuoteRepository:
        return quotes

    async def clients_dep() -> InMemoryClientRepository:
        return clients

    async def contracts_dep() -> InMemoryContractRepository:
        return contracts

    async def catalog_dep() -> FakeServiceLookup:
        return FakeServiceLookup()

    async def recorder_dep() -> RecordPayment:
        return RecordPayment(payments)

    async def history_dep() -> ContractPaymentEntries:
        return ContractPaymentEntries(payments)

    async def events_dep() -> InMemoryEventRepository:
        return events

    app = create_app(readiness_check=_no_database)
    app.dependency_overrides.update(
        {
            deps.get_quote_repository: quotes_dep,
            deps.get_client_repository: clients_dep,
            deps.get_contract_repository: contracts_dep,
            deps.get_service_lookup: catalog_dep,
            deps.get_payment_recorder: recorder_dep,
            deps.get_payments_lookup: history_dep,
            deps.get_payment_finder: lambda: FindPayment(payments),
            deps.get_payment_voider: lambda: VoidPayment(payments),
            deps.get_user_names: lambda: _names,
            deps.get_company_profile: lambda: CompanyProfile(name="Darze"),
            deps.get_event_repository: events_dep,
            deps.get_clock: lambda: clock,
            get_current_user: signed_in_as(Role.EVENTS_MANAGER),
        }
    )
    with TestClient(app) as client:
        yield Api(client, payments, customer)


def test_ca41_genera_contrato_desde_cotizacion_aceptada(api: Api) -> None:
    quote_id = api.accepted_quote(545_001)

    response = api.generate(quote_id)
    quote = api.client.get(f"/v1/quotes/{quote_id}").json()

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == "CON-2026-0001"
    assert body["status"] == "PENDING_SIGNATURE"
    assert (body["total_cents"], body["advance_cents"], body["balance_cents"]) == (
        545_001,
        272_501,
        272_500,
    )
    assert body["balance_due_date"] == "2026-12-12"
    assert body["quote_code"] == "COT-2026-0001"
    assert body["client_name"] == "José Ramírez"
    assert quote["contract_id"] == body["id"]


def test_ca41_1_errores_al_generar(api: Api) -> None:
    quote_id = api.accepted_quote()
    api.generate(quote_id)

    duplicated = api.generate(quote_id)
    invalid = api.generate(api.accepted_quote(), advance_cents=0)
    missing = api.generate("00000000-0000-0000-0000-000000000000")

    assert (duplicated.status_code, duplicated.json()["code"]) == (409, "contract.already_exists")
    assert (invalid.status_code, invalid.json()["code"]) == (422, "contract.advance_invalid")
    assert (missing.status_code, missing.json()["code"]) == (404, "contract.quote_not_found")


def test_ca42_firma_con_adelanto_y_pago_registrado(api: Api) -> None:
    contract_id = api.generate(api.accepted_quote(), advance_cents=200_000).json()["id"]

    response = api.sign(contract_id)
    again = api.sign(contract_id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SIGNED"
    assert body["can_become_event"] is True
    assert body["signature"]["signer_name"] == "José Ramírez"
    assert [(p["kind"], p["amount_cents"], p["method"]) for p in body["payments"]] == [
        ("ADVANCE", 200_000, "YAPE_PLIN")
    ]
    assert (again.status_code, again.json()["code"]) == (409, "contract.not_pending")
    assert len(api.payments.payments) == 1


def test_ca42_datos_invalidos_no_registran_pago(api: Api) -> None:
    contract_id = api.generate(api.accepted_quote()).json()["id"]

    no_signer = api.sign(contract_id, signer_name=" ")
    future = api.sign(
        contract_id, advance={"paid_on": "2030-01-01", "method": "CASH", "reference": None}
    )

    assert no_signer.json()["code"] == "contract.signer_required"
    assert (future.status_code, future.json()["code"]) == (422, "payment.date_in_future")
    assert api.payments.payments == []


def test_r_con_3_anula_firmado_con_devolucion(api: Api) -> None:
    contract_id = api.generate(api.accepted_quote()).json()["id"]
    api.sign(contract_id)
    url = f"/v1/contracts/{contract_id}/cancel"

    no_reason = api.client.post(url, json={"reason": " "})
    too_much = api.client.post(url, json={"reason": "Canceló", "refund_cents": 999_999_999})
    cancelled = api.client.post(
        url,
        json={
            "reason": "El cliente canceló",
            "refund_cents": 100_000,
            "refund": {"paid_on": "2026-11-22", "method": "CASH"},
            "note": "Acordado por teléfono",
        },
    )

    assert no_reason.json()["code"] == "contract.reason_required"
    assert too_much.json()["code"] == "contract.refund_invalid"
    body = cancelled.json()
    assert body["status"] == "CANCELLED"
    assert body["can_become_event"] is False
    assert body["cancellation"]["refund_cents"] == 100_000
    assert [p["kind"] for p in body["payments"]] == ["ADVANCE", "REFUND"]


def test_busca_contratos(api: Api) -> None:
    for _ in range(2):
        api.generate(api.accepted_quote())

    page = api.client.get("/v1/contracts", params={"text": "ramirez", "page_size": 1}).json()
    signed = api.client.get("/v1/contracts", params={"status": "SIGNED"}).json()

    assert (page["total"], len(page["items"])) == (2, 1)
    assert signed["total"] == 0


def test_r_con_4_permisos(api: Api) -> None:
    app = api.client.app
    app.dependency_overrides[get_current_user] = signed_in_as(Role.PURCHASING_MANAGER)  # type: ignore[attr-defined]

    response = api.client.get("/v1/contracts")

    assert (response.status_code, response.json()["code"]) == (403, "auth.forbidden")
