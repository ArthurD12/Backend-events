"""API de flujo de caja y resultado por evento (HU22): solo el administrador (`finance:read`)."""

from collections.abc import Iterator
from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.commercial.public_api import EventFinance
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.ledger.public_api import MonthlyCash, MovementCategory
from local_eventos.modules.reporting.presentation import dependencies as deps
from tests.unit.current_user import signed_in_as

EVENT_ID = uuid4()


async def _no_database() -> None:
    return None


async def _cash(date_from: date, date_to: date) -> list[MonthlyCash]:
    return [MonthlyCash(2026, 11, 300_000, 10_000, {MovementCategory.SUPPLIES: 50_000})]


async def _finance(event_id: UUID) -> EventFinance | None:
    if event_id != EVENT_ID:
        return None
    return EventFinance(
        event_id=EVENT_ID, event_code="EVT-2026-0001", event_date=date(2026, 12, 19),
        event_status="SCHEDULED", client_name="José", contract_id=uuid4(),
        contract_code="CON-2026-0001", total_cents=500_000, paid_cents=300_000,
        refunded_cents=0, balance_cents=200_000,
    )  # fmt: skip


async def _event_cash(event_id: UUID) -> dict[MovementCategory, int]:
    return {MovementCategory.STAFF: 70_000}


@pytest.fixture
def api() -> Iterator[TestClient]:
    app = create_app(readiness_check=_no_database)
    app.dependency_overrides.update(
        {
            deps.get_cash_totals: lambda: _cash,
            deps.get_event_finance: lambda: _finance,
            deps.get_event_cash: lambda: _event_cash,
            get_current_user: signed_in_as(Role.ADMIN),
        }
    )
    with TestClient(app) as client:
        yield client


def test_ca22_1_flujo_de_caja(api: TestClient) -> None:
    response = api.get("/v1/reports/cash-flow", params={"from": "2026-11-01", "to": "2026-11-30"})

    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["client_payments_cents"] == 290_000
    assert body["totals"]["expenses"]["supplies_cents"] == 50_000
    assert body["totals"]["net_cents"] == 240_000
    assert [m["month"] for m in body["months"]] == ["2026-11"]


def test_rango_invalido(api: TestClient) -> None:
    response = api.get("/v1/reports/cash-flow", params={"from": "2026-11-30", "to": "2026-11-01"})

    assert (response.status_code, response.json()["code"]) == (422, "report.range_invalid")


def test_ca22_3_resultado_del_evento(api: TestClient) -> None:
    body = api.get(f"/v1/reports/events/{EVENT_ID}/result").json()
    missing = api.get(f"/v1/reports/events/{uuid4()}/result")

    assert (body["collected_cents"], body["expense_cents"], body["result_cents"]) == (
        300_000,
        70_000,
        230_000,
    )
    assert body["balance_cents"] == 200_000
    assert (missing.status_code, missing.json()["code"]) == (404, "event.not_found")


@pytest.mark.parametrize("role", [Role.EVENTS_MANAGER, Role.PURCHASING_MANAGER])
def test_solo_el_administrador(api: TestClient, role: Role) -> None:
    api.app.dependency_overrides[get_current_user] = signed_in_as(role)  # type: ignore[attr-defined]

    assert api.get(f"/v1/reports/events/{EVENT_ID}/result").status_code == 403
    response = api.get("/v1/reports/cash-flow", params={"from": "2026-11-01", "to": "2026-11-30"})
    assert response.status_code == 403
