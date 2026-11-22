"""API del panel del administrador (HU31) con la consulta reemplazada por un fake."""

from collections.abc import Iterator
from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.commercial.domain.quotes.quote import EventType, QuoteStatus
from local_eventos.modules.commercial.public_api import QuoteStats, QuoteSummary
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.reporting.presentation.dependencies import get_quote_stats
from tests.unit.current_user import signed_in_as

CALLS: list[tuple[int | None, int | None]] = []


async def _no_database() -> None:
    return None


async def fake_stats(year: int | None = None, month: int | None = None) -> QuoteStats:
    CALLS.append((year, month))
    summary = QuoteSummary(
        id=uuid4(),
        code="COT-2026-0001",
        client_id=uuid4(),
        client_name="José Ramírez",
        event_type=EventType.WEDDING,
        event_date=date(2026, 12, 19),
        guests=120,
        total_cents=545_000,
        status=QuoteStatus.ACCEPTED,
        valid_until=date(2026, 12, 7),
    )
    return QuoteStats(
        year=year or 2026,
        month=month or 11,
        drafts=2,
        sent_pending=1,
        created_in_month=4,
        accepted_in_month=1,
        accepted_amount_cents=545_000,
        upcoming=[summary],
        recent=[summary],
    )


@pytest.fixture
def api() -> Iterator[TestClient]:
    CALLS.clear()

    async def stats_dep():  # type: ignore[no-untyped-def]
        return fake_stats

    app = create_app(readiness_check=_no_database)
    app.dependency_overrides[get_quote_stats] = stats_dep
    app.dependency_overrides[get_current_user] = signed_in_as(Role.ADMIN)
    with TestClient(app) as client:
        yield client


def test_ca31_admin_ve_el_panel_con_los_numeros(api: TestClient) -> None:
    response = api.get("/v1/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["month"] == "2026-11"
    assert body["quotes"]["drafts"] == 2
    assert body["quotes"]["accepted_amount_cents"] == 545_000
    assert body["quotes"]["upcoming"][0]["client_name"] == "José Ramírez"
    assert CALLS == [(None, None)]


def test_ca31_6_el_mes_se_elige(api: TestClient) -> None:
    response = api.get("/v1/dashboard", params={"month": "2027-01"})

    assert response.json()["month"] == "2027-01"
    assert CALLS == [(2027, 1)]


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "noviembre"])
def test_mes_invalido_responde_422(api: TestClient, month: str) -> None:
    assert api.get("/v1/dashboard", params={"month": month}).status_code == 422


@pytest.mark.parametrize("role", [Role.EVENTS_MANAGER, Role.PURCHASING_MANAGER])
def test_ca31_5_solo_el_administrador(api: TestClient, role: Role) -> None:
    api.app.dependency_overrides[get_current_user] = signed_in_as(role)  # type: ignore[attr-defined]

    response = api.get("/v1/dashboard")

    assert (response.status_code, response.json()["code"]) == (403, "auth.forbidden")
