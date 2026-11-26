"""API de compras (HU27–HU29) con piezas en memoria. Sin base de datos."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.commercial.public_api import CompanyProfile
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.purchasing.infrastructure.purchase_pdf import (
    ReportLabPurchaseRenderer,
)
from local_eventos.modules.purchasing.presentation import dependencies as deps
from tests.unit.current_user import signed_in_as
from tests.unit.inventory.fakes import FakeClock, FakeEventLookup

from .fakes import (
    FakeExpenses,
    FakeInventory,
    FakeRequirement,
    InMemoryPurchaseRepository,
    InMemorySupplierRepository,
)


async def _no_database() -> None:
    return None


@dataclass
class Api:
    client: TestClient
    inventory: FakeInventory
    requirement: FakeRequirement
    expenses: FakeExpenses
    events: FakeEventLookup
    app: FastAPI

    def supplier(self, number: str = "20123456789", **changes: Any) -> dict[str, Any]:
        body = {"name": "Distribuidora Lima", "document_type": "RUC",
                "document_number": number, "phone": "987654321", **changes}  # fmt: skip
        response = self.client.post("/v1/purchasing/suppliers", json=body)
        assert response.status_code == 201, response.text
        result: dict[str, Any] = response.json()
        return result

    def request(self, *lines: tuple[str, str]) -> dict[str, Any]:
        response = self.client.post(
            "/v1/purchasing/purchases",
            json={"lines": [{"product_id": p, "quantity": q} for p, q in lines]},
        )
        assert response.status_code == 201, response.text
        result: dict[str, Any] = response.json()
        return result


@pytest.fixture
def api() -> Iterator[Api]:
    app = create_app(readiness_check=_no_database)
    suppliers, purchases = InMemorySupplierRepository(), InMemoryPurchaseRepository()
    inventory = FakeInventory()
    requirement, expenses, events = FakeRequirement(inventory), FakeExpenses(), FakeEventLookup()
    app.dependency_overrides[deps.get_supplier_repository] = lambda: suppliers
    app.dependency_overrides[deps.get_purchase_repository] = lambda: purchases
    app.dependency_overrides[deps.get_product_lookup] = lambda: inventory.lookup
    app.dependency_overrides[deps.get_low_stock_lookup] = lambda: inventory.low_stock
    app.dependency_overrides[deps.get_stock_receiver] = lambda: inventory.receive
    app.dependency_overrides[deps.get_event_requirement] = lambda: requirement
    app.dependency_overrides[deps.get_expense_recorder] = lambda: expenses
    app.dependency_overrides[deps.get_event_lookup] = lambda: events
    app.dependency_overrides[deps.get_document_renderer] = lambda: ReportLabPurchaseRenderer(
        compress=False
    )
    app.dependency_overrides[deps.get_company_profile] = lambda: CompanyProfile(
        name="Darze Catering", ruc="20999999999"
    )
    app.dependency_overrides[deps.get_clock] = FakeClock
    app.dependency_overrides[get_current_user] = signed_in_as(Role.PURCHASING_MANAGER)
    with TestClient(app) as client:
        yield Api(client, inventory, requirement, expenses, events, app)


def test_hu27_proveedores_documento_unico_busqueda_y_desactivar(api: Api) -> None:
    created = api.supplier(name="Avícola Ñaña SAC", email="VENTAS@avicola.pe")
    repeated = api.client.post(
        "/v1/purchasing/suppliers",
        json={"name": "Otro", "document_type": "RUC", "document_number": "20123456789",
              "phone": "987654321"},
    )  # fmt: skip
    invalid = api.client.post(
        "/v1/purchasing/suppliers",
        json={"name": "Otro", "document_type": "DNI", "document_number": "123", "phone": "9"},
    )
    found = api.client.get("/v1/purchasing/suppliers", params={"text": "avicola nana"})
    off = api.client.post(f"/v1/purchasing/suppliers/{created['id']}/deactivate")
    updated = api.client.put(
        f"/v1/purchasing/suppliers/{created['id']}",
        json={"name": "Avícola Ñaña", "document_type": "RUC", "document_number": "20123456789",
              "phone": "01 4455667", "address": "Av. Lima 123"},
    )  # fmt: skip

    assert created["email"] == "ventas@avicola.pe"
    assert (repeated.status_code, repeated.json()["code"]) == (409, "purchasing.document_taken")
    assert (invalid.status_code, invalid.json()["code"]) == (422, "purchasing.validation")
    assert [s["id"] for s in found.json()] == [created["id"]]
    assert off.json()["active"] is False
    assert api.client.get("/v1/purchasing/suppliers").json() == []
    assert updated.json()["phone"] == "014455667"
    assert api.client.get(f"/v1/purchasing/suppliers/{uuid4()}").status_code == 404


def test_hu28_faltantes_y_solicitud(api: Api) -> None:
    sugar = api.inventory.add("AZU-01")
    api.inventory.short(sugar, "2.5", "10")

    shortages = api.client.get("/v1/purchasing/shortages").json()
    purchase = api.request((str(sugar), shortages[0]["suggested_quantity"]))

    assert shortages == [
        {"product_id": str(sugar), "code": "AZU-01", "name": "Producto AZU-01", "unit": "KG",
         "stock": "2.500", "min_stock": "10.000", "suggested_quantity": "7.500"}
    ]  # fmt: skip
    assert purchase["code"] == "COM-2026-0001" and purchase["status"] == "REQUESTED"
    assert purchase["lines"][0]["quantity"] == "7.500"
    assert purchase["lines"][0]["product_code"] == "AZU-01"
    assert purchase["total_cents"] is None


def test_hu29_ordenar_recibir_una_vez_y_entradas(api: Api) -> None:
    sugar = str(api.inventory.add("AZU-01"))
    supplier = api.supplier()
    purchase = api.request((sugar, "10"))
    url = f"/v1/purchasing/purchases/{purchase['id']}"

    early = api.client.post(f"{url}/receive", json={"lines": []})
    ordered = api.client.post(
        f"{url}/order",
        json={"supplier_id": supplier["id"], "lines": [{"product_id": sugar,
              "unit_cost_cents": 380}]},
    )  # fmt: skip
    body = {"lines": [{"product_id": sugar, "received_quantity": "9.5", "lot": "L-1",
                       "expires_on": "2027-01-01"}], "invoice_number": "F001-12"}  # fmt: skip
    received = api.client.post(f"{url}/receive", json=body)
    again = api.client.post(f"{url}/receive", json=body)
    cancel = api.client.post(f"{url}/cancel", json={"reason": "tarde"})
    listed = api.client.get("/v1/purchasing/purchases", params={"status": "RECEIVED"})

    assert (early.status_code, early.json()["code"]) == (409, "purchasing.invalid_transition")
    assert ordered.json()["status"] == "ORDERED" and ordered.json()["total_cents"] == 3800
    assert ordered.json()["supplier_name"] == "Distribuidora Lima"
    assert received.json()["status"] == "RECEIVED" and received.json()["total_cents"] == 3610
    assert received.json()["lines"][0]["received_quantity"] == "9.500"
    assert received.json()["invoice_number"] == "F001-12"
    assert again.json()["code"] == "purchasing.invalid_transition"
    assert cancel.json()["code"] == "purchasing.invalid_transition"
    assert len(api.inventory.received) == 1
    assert api.inventory.received[0].supplier_id is not None
    assert listed.json()["total"] == 1


def test_proveedor_inactivo_y_cancelar(api: Api) -> None:
    sugar = str(api.inventory.add("AZU-01"))
    supplier = api.supplier()
    api.client.post(f"/v1/purchasing/suppliers/{supplier['id']}/deactivate")
    purchase = api.request((sugar, "1"))
    url = f"/v1/purchasing/purchases/{purchase['id']}"

    inactive = api.client.post(
        f"{url}/order",
        json={"supplier_id": supplier["id"], "lines": [{"product_id": sugar,
              "unit_cost_cents": 1}]},
    )  # fmt: skip
    cancelled = api.client.post(f"{url}/cancel", json={"reason": "Ya no se necesita"})

    assert (inactive.status_code, inactive.json()["code"]) == (409, "purchasing.supplier_inactive")
    assert cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["cancel_reason"] == "Ya no se necesita"
    assert api.client.get(f"/v1/purchasing/purchases/{uuid4()}").status_code == 404


def test_encargado_de_eventos_no_entra_a_compras(api: Api) -> None:
    api.client.app.dependency_overrides[get_current_user] = signed_in_as(  # type: ignore[attr-defined]
        Role.EVENTS_MANAGER
    )

    assert api.client.get("/v1/purchasing/suppliers").status_code == 403
    assert api.client.get("/v1/purchasing/purchases").status_code == 403
    assert api.client.get("/v1/purchasing/shortages").status_code == 403
