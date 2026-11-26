"""Compra desde los faltantes del evento, PDF y egreso único (HU25, HU30, 021)."""

from typing import Any
from uuid import uuid4

from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from local_eventos.modules.ledger.public_api import MovementCategory, MovementType
from tests.unit.current_user import signed_in_as

from .test_purchasing_api import Api, api  # noqa: F401


def _received(api: Api, event_id: Any = None) -> dict[str, Any]:  # noqa: F811
    """Una compra de S/ 36.10 ya recibida (9.5 kg a S/ 3.80)."""
    sugar = str(api.inventory.add("AZU-01"))
    supplier = api.supplier()
    purchase = api.request((sugar, "10"))
    url = f"/v1/purchasing/purchases/{purchase['id']}"
    api.client.post(
        f"{url}/order",
        json={
            "supplier_id": supplier["id"],
            "lines": [{"product_id": sugar, "unit_cost_cents": 380}],
        },
    )
    received = api.client.post(
        f"{url}/receive",
        json={
            "lines": [{"product_id": sugar, "received_quantity": "9.5"}],
            "invoice_number": "F001-12",
        },
    )
    assert received.status_code == 200, received.text
    result: dict[str, Any] = received.json()
    return result


def test_ca25_6_solicitud_con_los_faltantes_vinculada_al_evento(api: Api) -> None:  # noqa: F811
    rice, sugar = api.inventory.add("ARR-01"), api.inventory.add("AZU-01")
    covered = api.inventory.add("SAL-01")
    event_id = api.requirement.add("EVT-2026-0009", [(rice, "8"), (sugar, "2.5"), (covered, "0")])

    response = api.client.post(f"/v1/purchasing/purchases/from-event/{event_id}")

    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "REQUESTED"
    assert body["event_id"] == str(event_id)
    assert body["notes"] == "Faltantes del evento EVT-2026-0009"
    assert {line["product_code"]: line["quantity"] for line in body["lines"]} == {
        "ARR-01": "8.000",
        "AZU-01": "2.500",
    }  # lo ya cubierto no se pide
    listed = api.client.get("/v1/purchasing/purchases", params={"event_id": str(event_id)})
    assert listed.json()["total"] == 1


def test_sin_faltantes_o_evento_inexistente_no_crea_compra(api: Api) -> None:  # noqa: F811
    rice = api.inventory.add("ARR-01")
    covered = api.requirement.add("EVT-2026-0001", [(rice, "0")])
    finished = api.requirement.add("EVT-2026-0002", [], calculated=False)

    none = api.client.post(f"/v1/purchasing/purchases/from-event/{covered}")
    not_calculated = api.client.post(f"/v1/purchasing/purchases/from-event/{finished}")
    missing = api.client.post(f"/v1/purchasing/purchases/from-event/{uuid4()}")

    assert (none.status_code, none.json()["code"]) == (409, "purchasing.no_shortages")
    assert not_calculated.json()["code"] == "purchasing.no_shortages"
    assert (missing.status_code, missing.json()["code"]) == (404, "purchasing.event_not_found")


def test_ca30_2_pdf_de_la_compra_con_codigo_total_y_evento(api: Api) -> None:  # noqa: F811
    received = _received(api)
    pdf = api.client.get(f"/v1/purchasing/purchases/{received['id']}/pdf")

    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert f'filename="{received["code"]}.pdf"' in pdf.headers["content-disposition"]
    assert pdf.content.startswith(b"%PDF")
    for text in (received["code"], "S/ 36.10", "ORDEN DE COMPRA", "Darze Catering", "F001-12"):
        assert text.encode() in pdf.content, text
    assert api.client.get(f"/v1/purchasing/purchases/{uuid4()}/pdf").status_code == 404


def test_ca30_2_pdf_nombra_el_evento_de_la_compra(api: Api) -> None:  # noqa: F811
    rice = api.inventory.add("ARR-01")
    event_id = api.events.add()
    code = api.events.events[event_id].code
    api.requirement.add(code, [(rice, "3")], event_id=event_id)
    created = api.client.post(f"/v1/purchasing/purchases/from-event/{event_id}").json()

    pdf = api.client.get(f"/v1/purchasing/purchases/{created['id']}/pdf")

    assert code.encode() in pdf.content


def test_ca30_3_egreso_una_sola_vez_con_monto_evento_y_concepto(api: Api) -> None:  # noqa: F811
    api.app.dependency_overrides[get_current_user] = signed_in_as(Role.ADMIN)
    received = _received(api)
    url = f"/v1/purchasing/purchases/{received['id']}/expense"

    first = api.client.post(url, json={"method": "TRANSFER"})
    again = api.client.post(url, json={})

    assert first.status_code == 200
    assert first.json()["expense_movement_id"] is not None
    assert (again.status_code, again.json()["code"]) == (
        409,
        "purchasing.expense_already_registered",
    )
    assert len(api.expenses.requests) == 1
    request = api.expenses.requests[0]
    assert (request.type, request.category) == (MovementType.EXPENSE, MovementCategory.SUPPLIES)
    assert request.amount_cents == 3610
    assert request.concept == f"Compra {received['code']}"
    assert request.reference == "F001-12"  # por defecto, la factura


def test_ca30_3_solo_una_compra_recibida_se_registra_como_egreso(api: Api) -> None:  # noqa: F811
    api.app.dependency_overrides[get_current_user] = signed_in_as(Role.ADMIN)
    sugar = str(api.inventory.add("AZU-01"))
    requested = api.request((sugar, "5"))

    response = api.client.post(f"/v1/purchasing/purchases/{requested['id']}/expense", json={})

    assert (response.status_code, response.json()["code"]) == (
        409,
        "purchasing.expense_not_available",
    )
    assert api.expenses.requests == []


def test_egreso_exige_tambien_payments_record(api: Api) -> None:  # noqa: F811
    received = _received(api)  # el encargado de compras no puede registrar pagos

    response = api.client.post(f"/v1/purchasing/purchases/{received['id']}/expense", json={})

    assert response.status_code == 403
    assert api.expenses.requests == []
