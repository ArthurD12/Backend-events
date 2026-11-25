"""API de inventario (HU23, HU26) con piezas en memoria. Sin base de datos."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.commercial.public_api import EventStatus
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.inventory.presentation import dependencies as deps
from tests.unit.current_user import signed_in_as

from .fakes import (
    FakeClock,
    FakeEventLookup,
    InMemoryMovementRepository,
    InMemoryProductRepository,
    InMemoryStockRepository,
)


async def _no_database() -> None:
    return None


@dataclass
class Api:
    client: TestClient
    events: FakeEventLookup

    def product(self, code: str = "PLA-01", **changes: Any) -> dict[str, Any]:
        body = {
            "code": code,
            "name": "Plato llano",
            "category": "DINNERWARE",
            "unit": "UNIT",
            "kind": "REUSABLE",
            "min_stock": "10",
            **changes,
        }
        response = self.client.post("/v1/inventory/products", json=body)
        assert response.status_code == 201, response.text
        result: dict[str, Any] = response.json()
        return result

    def move(self, kind: str, **body: Any) -> Any:
        return self.client.post(f"/v1/inventory/movements/{kind}", json=body)


@pytest.fixture
def api() -> Iterator[Api]:
    app = create_app(readiness_check=_no_database)
    products, stock = InMemoryProductRepository(), InMemoryStockRepository()
    movements, events = InMemoryMovementRepository(), FakeEventLookup()
    app.dependency_overrides[deps.get_product_repository] = lambda: products
    app.dependency_overrides[deps.get_stock_repository] = lambda: stock
    app.dependency_overrides[deps.get_movement_repository] = lambda: movements
    app.dependency_overrides[deps.get_event_lookup] = lambda: events
    app.dependency_overrides[deps.get_clock] = FakeClock
    app.dependency_overrides[get_current_user] = signed_in_as(Role.PURCHASING_MANAGER)
    with TestClient(app) as client:
        yield Api(client, events)


def test_ca23_1_crea_producto_con_stock_cero_como_texto_decimal(api: Api) -> None:
    created = api.product(code="pla-01", min_stock="12.5")

    assert created["code"] == "PLA-01"
    assert created["min_stock"] == "12.500"
    assert created["stock"] == "0.000"
    assert created["is_low_stock"] is True and created["currency"] == "PEN"


def test_ca23_1_codigo_repetido_y_datos_invalidos(api: Api) -> None:
    api.product()

    repeated = api.client.post(
        "/v1/inventory/products",
        json={"code": "PLA-01", "name": "Otro", "category": "OTHER", "unit": "BOX",
              "kind": "CONSUMABLE"},
    )  # fmt: skip
    invalid = api.client.post(
        "/v1/inventory/products",
        json={"code": "X", "name": "Otro", "category": "OTHER", "unit": "BOX",
              "kind": "CONSUMABLE", "min_stock": "1.2345"},
    )  # fmt: skip

    assert (repeated.status_code, repeated.json()["code"]) == (409, "inventory.code_taken")
    assert (invalid.status_code, invalid.json()["code"]) == (422, "inventory.validation")


def test_ca23_entrada_salida_devolucion_y_materiales_del_evento(api: Api) -> None:
    plate = api.product()
    event = str(api.events.add(EventStatus.CONFIRMED))

    entry = api.move("entry", product_id=plate["id"], quantity="100", unit_cost_cents=250,
                     lot="L-1", expires_on="2027-01-10")  # fmt: skip
    out = api.move("exit", product_id=plate["id"], event_id=event, quantity="40")
    back = api.move("return", product_id=plate["id"], event_id=event, quantity="35")
    lost = api.move("waste", product_id=plate["id"], event_id=event, quantity="2", reason="rotos")
    materials = api.client.get(f"/v1/inventory/events/{event}/materials")
    detail = api.client.get(f"/v1/inventory/products/{plate['id']}")
    history = api.client.get(f"/v1/inventory/products/{plate['id']}/movements")

    assert entry.status_code == 201
    assert entry.json()["movement"]["unit_cost_cents"] == 250
    assert out.json()["stock"] == "60.000"
    assert out.json()["movement"]["stock_delta"] == "-40.000"
    assert back.json()["stock"] == "95.000"
    assert lost.json()["movement"]["stock_delta"] == "0.000"
    assert materials.json() == [
        {
            "product_id": plate["id"], "code": "PLA-01", "name": "Plato llano", "unit": "UNIT",
            "kind": "REUSABLE", "out": "40.000", "returned": "35.000", "wasted": "2.000",
            "pending_return": "3.000",
        }
    ]  # fmt: skip
    assert detail.json()["stock"] == "95.000"
    assert detail.json()["stock_value_cents"] == 23750
    assert history.json()["total"] == 4
    assert history.json()["items"][0]["kind"] == "WASTE"


def test_ca26_errores_con_su_code(api: Api) -> None:
    plate = api.product()
    event = str(api.events.add())
    api.move("entry", product_id=plate["id"], quantity="5", unit_cost_cents=100)

    too_much = api.move("exit", product_id=plate["id"], event_id=event, quantity="6")
    finished = api.move(
        "exit", product_id=plate["id"], quantity="1",
        event_id=str(api.events.add(EventStatus.FINISHED)),
    )  # fmt: skip
    no_event = api.move("exit", product_id=plate["id"], event_id=str(uuid4()), quantity="1")
    no_exit = api.move("return", product_id=plate["id"], event_id=event, quantity="1")
    no_reason = api.move("waste", product_id=plate["id"], quantity="1", reason=" ")
    adjust = api.move("adjustment", product_id=plate["id"], quantity="-1.5", reason="conteo")
    missing = api.client.get(f"/v1/inventory/products/{uuid4()}")
    bad_text = api.move("exit", product_id=plate["id"], event_id=event, quantity="-1")

    assert (too_much.status_code, too_much.json()["code"]) == (409, "inventory.insufficient_stock")
    assert "5.000" in too_much.json()["detail"]
    assert finished.json()["code"] == "inventory.event_not_assignable"
    assert (no_event.status_code, no_event.json()["code"]) == (404, "inventory.event_not_found")
    assert no_exit.json()["code"] == "inventory.return_exceeds"
    assert no_reason.json()["code"] == "inventory.validation"
    assert adjust.json()["stock"] == "3.500"
    assert (missing.status_code, missing.json()["code"]) == (404, "inventory.product_not_found")
    assert bad_text.status_code == 422


def test_ca23_3_desactivar_y_filtrar_alertas(api: Api) -> None:
    plate = api.product()
    milk = api.product("LEC-01", name="Leche", kind="CONSUMABLE", unit="LITER", min_stock="0")
    api.move("entry", product_id=milk["id"], quantity="10", unit_cost_cents=400,
             expires_on="2026-12-01")  # fmt: skip

    deactivated = api.client.post(f"/v1/inventory/products/{plate['id']}/deactivate")
    entry = api.move("entry", product_id=plate["id"], quantity="1", unit_cost_cents=1)
    listed = api.client.get("/v1/inventory/products").json()
    alerts = api.client.get("/v1/inventory/products", params={"alerts_only": True}).json()
    activated = api.client.post(f"/v1/inventory/products/{plate['id']}/activate")
    updated = api.client.put(
        f"/v1/inventory/products/{plate['id']}",
        json={"code": "PLA-02", "name": "Plato hondo", "category": "DINNERWARE", "unit": "UNIT",
              "kind": "REUSABLE", "min_stock": "5"},
    )  # fmt: skip

    assert deactivated.json()["active"] is False
    assert entry.json()["code"] == "inventory.product_inactive"
    assert [p["code"] for p in listed] == ["LEC-01"]
    assert [p["code"] for p in alerts] == ["LEC-01"] and alerts[0]["expiring_soon"]
    assert alerts[0]["next_expiry"] == "2026-12-01"
    assert activated.json()["active"] is True
    assert updated.json()["code"] == "PLA-02" and updated.json()["min_stock"] == "5.000"


def _as(api: Api, role: Role) -> None:
    api.client.app.dependency_overrides[get_current_user] = signed_in_as(role)  # type: ignore[attr-defined]


def test_encargado_de_eventos_solo_consulta(api: Api) -> None:
    plate = api.product()
    event = str(api.events.add())
    _as(api, Role.EVENTS_MANAGER)

    assert api.client.get("/v1/inventory/products").status_code == 200
    assert api.client.get(f"/v1/inventory/products/{plate['id']}/movements").status_code == 200
    assert api.client.get(f"/v1/inventory/events/{event}/materials").status_code == 200
    assert api.client.post("/v1/inventory/products", json={}).status_code == 403
    assert api.move("exit", product_id=plate["id"], event_id=event, quantity="1").status_code == 403


def test_responsable_es_quien_registra(api: Api) -> None:
    plate = api.product()
    response = api.move("entry", product_id=plate["id"], quantity="1", unit_cost_cents=1)

    assert UUID(response.json()["movement"]["recorded_by"])
