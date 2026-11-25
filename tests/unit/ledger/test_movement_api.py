"""API de ingresos y egresos (HU21) con piezas en memoria. Sin base de datos."""

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.ledger.presentation import dependencies as deps
from tests.unit.current_user import signed_in_as

from .fakes import FakeLedgerClock, InMemoryMovementRepository


async def _no_database() -> None:
    return None


async def _names(user_ids: Any) -> dict[Any, str]:
    return {user_id: "Ana" for user_id in user_ids}


@pytest.fixture
def api() -> Iterator[TestClient]:
    movements = InMemoryMovementRepository()

    async def movements_dep() -> InMemoryMovementRepository:
        return movements

    app = create_app(readiness_check=_no_database)
    app.dependency_overrides.update(
        {
            deps.get_movement_repository: movements_dep,
            deps.get_clock: FakeLedgerClock,
            deps.get_user_names: lambda: _names,
            get_current_user: signed_in_as(Role.EVENTS_MANAGER),
        }
    )
    with TestClient(app) as client:
        yield client


def _expense(**changes: Any) -> dict[str, Any]:
    return {
        "type": "EXPENSE",
        "category": "SUPPLIES",
        "concept": "Carne",
        "amount_cents": 80_000,
        "method": "CASH",
        "occurred_on": "2026-11-20",
        **changes,
    }


def test_ca21_registrar_filtrar_y_anular(api: TestClient) -> None:
    event_id = str(uuid4())
    expense = api.post("/v1/movements", json=_expense(event_id=event_id))
    income = api.post(
        "/v1/movements",
        json=_expense(type="INCOME", category="OTHER_INCOME", concept="Alquiler de menaje"),
    ).json()

    voided = api.post(f"/v1/movements/{income['id']}/void", json={"reason": "Duplicado"})
    again = api.post(f"/v1/movements/{income['id']}/void", json={"reason": "Duplicado"})
    by_event = api.get("/v1/movements", params={"event_id": event_id}).json()
    active = api.get("/v1/movements", params={"state": "ACTIVE"}).json()

    assert expense.status_code == 201
    assert expense.json()["recorded_by_name"] == "Ana" and expense.json()["void"] is None
    assert voided.status_code == 200 and voided.json()["void"]["reason"] == "Duplicado"
    assert (again.status_code, again.json()["code"]) == (409, "movement.already_voided")
    assert [m["id"] for m in by_event["items"]] == [expense.json()["id"]]
    assert active["total"] == 1


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"category": "OTHER_INCOME"}, "movement.category_invalid"),
        ({"occurred_on": "2026-11-23"}, "movement.date_in_future"),
        ({"amount_cents": 0}, "movement.amount_invalid"),
    ],
)
def test_datos_invalidos(api: TestClient, changes: dict[str, Any], code: str) -> None:
    response = api.post("/v1/movements", json=_expense(**changes))

    assert (response.status_code, response.json()["code"]) == (422, code)


def test_anular_inexistente(api: TestClient) -> None:
    response = api.post(f"/v1/movements/{uuid4()}/void", json={"reason": "x"})

    assert (response.status_code, response.json()["code"]) == (404, "movement.not_found")


def test_compras_no_ve_dinero(api: TestClient) -> None:
    api.app.dependency_overrides[get_current_user] = signed_in_as(Role.PURCHASING_MANAGER)  # type: ignore[attr-defined]

    assert api.get("/v1/movements").status_code == 403
    assert api.post("/v1/movements", json=_expense()).status_code == 403
