"""API de reportes (HU32–HU34): JSON, CSV y PDF de la misma tabla, y permisos por reporte."""

import csv
from collections.abc import Iterator
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.commercial.public_api import CompanyProfile
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.reporting.infrastructure.csv_exporter import CsvExporter
from local_eventos.modules.reporting.infrastructure.pdf_exporter import PdfExporter
from local_eventos.modules.reporting.presentation import dependencies as deps
from tests.unit.current_user import signed_in_as

from . import report_fakes as fakes

NOV = {"from": "2026-11-01", "to": "2026-11-30"}


async def _no_database() -> None:
    return None


@pytest.fixture
def api() -> Iterator[TestClient]:
    app = create_app(readiness_check=_no_database)
    app.dependency_overrides.update(
        {
            deps.get_events_report: lambda: fakes.FakeEvents(),
            deps.get_cash_entries: lambda: fakes.cash_entries,
            deps.get_event_refs: lambda: fakes.event_refs,
            deps.get_stock_report: lambda: fakes.stock,
            deps.get_movements_report: lambda: fakes.movements,
            deps.get_purchases_report: lambda: fakes.purchases,
            deps.get_clock: lambda: fakes.FixedClock(),
            deps.get_company: lambda: CompanyProfile(name="Darze"),
            deps.get_exporters: lambda: {
                "csv": CsvExporter(),
                "pdf": PdfExporter(compress=False),
            },
            get_current_user: signed_in_as(Role.ADMIN),
        }
    )
    with TestClient(app) as client:
        yield client


def _as(api: TestClient, role: Role) -> None:
    api.app.dependency_overrides[get_current_user] = signed_in_as(role)  # type: ignore[attr-defined]


def test_ca32_1_eventos_en_json(api: TestClient) -> None:
    response = api.get("/v1/reports/events", params={**NOV, "status": "SCHEDULED"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["report"] == "events" and body["currency"] == "PEN"
    assert [c["key"] for c in body["columns"]][:2] == ["code", "event_date"]
    assert body["rows"][0]["event_date"] == "2026-12-19"
    assert body["rows"][0]["total"] == 1_000_000
    assert {f["label"]: f["value"] for f in body["filters"]}["Estado"] == "Programado"
    assert {t["key"]: t["value"] for t in body["totals"]}["balance"] == 200_000


def test_ca32_1_sin_payments_record_montos_null(api: TestClient) -> None:
    _as(api, Role.PURCHASING_MANAGER)  # tiene events:read, no payments:record

    body = api.get("/v1/reports/events", params=NOV).json()

    assert {r["total"] for r in body["rows"]} == {None}
    assert {t["key"]: t["value"] for t in body["totals"]}["paid"] is None


def test_ca33_1_y_ca34_2_csv_con_las_mismas_filas_que_el_json(api: TestClient) -> None:
    body = api.get("/v1/reports/cash", params=NOV).json()
    response = api.get("/v1/reports/cash", params={**NOV, "format": "csv"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="reporte-cash-2026-11-25.csv"' in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert rows[0] == [c["label"] for c in body["columns"]]
    assert len(rows[1 : 1 + len(body["rows"])]) == len(body["rows"])
    assert [r[3] for r in rows[1 : 1 + len(body["rows"])]] == [r["concept"] for r in body["rows"]]
    assert rows[-1] == ["Saldo del periodo", "4000,00"]


def test_ca34_1_pdf(api: TestClient) -> None:
    response = api.get("/v1/reports/purchases", params={**NOV, "format": "pdf"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert b"COM-2026-0001" in response.content and b"TOTALES" in response.content


def test_almacen_stock_y_movimientos(api: TestClient) -> None:
    _as(api, Role.PURCHASING_MANAGER)

    stock = api.get("/v1/reports/inventory", params={"category": "DINNERWARE"}).json()
    moves = api.get("/v1/reports/inventory-movements", params={**NOV, "kind": "ENTRY"}).json()

    assert stock["rows"][0]["stock"] == "8.000" and stock["rows"][0]["low_stock"] is True
    assert moves["rows"][1]["event"] == "EVT-2026-0001"


@pytest.mark.parametrize("path", ["events", "cash", "inventory-movements", "purchases"])
def test_r_rep_2_rango_mayor_a_366_dias(api: TestClient, path: str) -> None:
    response = api.get(f"/v1/reports/{path}", params={"from": "2026-01-01", "to": "2027-01-02"})

    assert (response.status_code, response.json()["code"]) == (422, "report.range_invalid")


def test_ca32_5_personal_no_disponible(api: TestClient) -> None:
    response = api.get("/v1/reports/staff", params={"format": "csv"})

    assert (response.status_code, response.json()["code"]) == (503, "report.unavailable")


@pytest.mark.parametrize(
    ("role", "path", "status"),
    [
        (Role.EVENTS_MANAGER, "cash", 403),
        (Role.PURCHASING_MANAGER, "cash", 403),
        (Role.EVENTS_MANAGER, "purchases", 403),
        (Role.PURCHASING_MANAGER, "staff", 403),
        (Role.EVENTS_MANAGER, "events", 200),
        (Role.EVENTS_MANAGER, "inventory", 200),
        (Role.PURCHASING_MANAGER, "purchases", 200),
    ],
)
def test_permisos_por_reporte(api: TestClient, role: Role, path: str, status: int) -> None:
    _as(api, role)

    assert api.get(f"/v1/reports/{path}", params=NOV).status_code == status


def test_formato_desconocido_422(api: TestClient) -> None:
    assert api.get("/v1/reports/cash", params={**NOV, "format": "xlsx"}).status_code == 422
