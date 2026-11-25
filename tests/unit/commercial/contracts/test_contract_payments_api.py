"""API de pagos del contrato y comprobante (HU19, HU20) con piezas en memoria."""

from typing import Any

import pytest

from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from tests.unit.current_user import signed_in_as

from .test_contract_api import Api, api  # noqa: F401 - fixture


def _signed(api: Api) -> dict[str, Any]:  # noqa: F811
    contract = api.generate(api.accepted_quote(500_000)).json()
    signed: dict[str, Any] = api.sign(contract["id"]).json()
    return signed


def _pay(api: Api, contract_id: str, amount: int) -> Any:  # noqa: F811
    return api.client.post(
        f"/v1/contracts/{contract_id}/payments",
        json={"amount_cents": amount, "paid_on": "2026-11-22", "method": "CASH"},
    )


def test_ca19_registrar_pago_ver_cuenta_y_saldo(api: Api) -> None:  # noqa: F811
    contract = _signed(api)

    created = _pay(api, contract["id"], 100_000)
    account = api.client.get(f"/v1/contracts/{contract['id']}/account").json()
    detail = api.client.get(f"/v1/contracts/{contract['id']}").json()

    assert created.status_code == 201
    body = created.json()
    assert body["payment"]["number"] == "PAG-2026-0002"
    assert body["payment"]["recorded_by_name"] == "Usuario de prueba"
    assert body["payment"]["voidable"] is True
    assert (account["total_cents"], account["paid_cents"], account["balance_cents"]) == (
        500_000,
        350_000,
        150_000,
    )
    assert account["balance_due_date"] == "2026-12-12" and account["overdue"] is False
    assert [p["kind"] for p in account["payments"]] == ["ADVANCE", "INSTALLMENT"]
    assert account["payments"][0]["voidable"] is False
    assert (detail["paid_cents"], detail["balance_cents"]) == (350_000, 150_000)


def test_ca19_2_no_supera_el_saldo(api: Api) -> None:  # noqa: F811
    contract = _signed(api)

    response = _pay(api, contract["id"], 250_001)

    assert (response.status_code, response.json()["code"]) == (422, "payment.exceeds_balance")


def test_ca19_6_sin_pagos_en_contrato_pendiente(api: Api) -> None:  # noqa: F811
    contract = api.generate(api.accepted_quote(500_000)).json()

    response = _pay(api, contract["id"], 1)

    assert (response.status_code, response.json()["code"]) == (409, "contract.not_signed")
    assert contract["balance_cents"] == 250_000  # pendiente: total − adelanto
    assert contract["paid_cents"] == 0


def test_ca19_5_anular_pago_y_errores(api: Api) -> None:  # noqa: F811
    contract = _signed(api)
    payment = _pay(api, contract["id"], 100_000).json()["payment"]
    advance_id = api.client.get(f"/v1/contracts/{contract['id']}/account").json()["payments"][0][
        "id"
    ]

    voided = api.client.post(f"/v1/payments/{payment['id']}/void", json={"reason": "Error"})
    again = api.client.post(f"/v1/payments/{payment['id']}/void", json={"reason": "Error"})
    advance = api.client.post(f"/v1/payments/{advance_id}/void", json={"reason": "x"})
    other = _pay(api, contract["id"], 1_000).json()["payment"]
    no_reason = api.client.post(f"/v1/payments/{other['id']}/void", json={"reason": " "})
    missing = api.client.post(
        "/v1/payments/00000000-0000-0000-0000-000000000000/void", json={"reason": "x"}
    )

    assert voided.status_code == 200
    body = voided.json()
    assert body["balance_cents"] == 250_000
    assert body["payments"][1]["void"]["reason"] == "Error"
    assert (again.status_code, again.json()["code"]) == (409, "payment.already_voided")
    assert (advance.status_code, advance.json()["code"]) == (409, "payment.not_voidable")
    assert (no_reason.status_code, no_reason.json()["code"]) == (422, "payment.reason_required")
    assert (missing.status_code, missing.json()["code"]) == (404, "payment.not_found")


def test_ca20_comprobante_pdf(api: Api) -> None:  # noqa: F811
    contract = _signed(api)
    payment = _pay(api, contract["id"], 100_000).json()["payment"]

    response = api.client.get(f"/v1/payments/{payment['id']}/receipt.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="PAG-2026-0002.pdf"' in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/v1/contracts/00000000-0000-0000-0000-000000000000/account"),
        ("post", "/v1/contracts/00000000-0000-0000-0000-000000000000/payments"),
        ("post", "/v1/payments/00000000-0000-0000-0000-000000000000/void"),
        ("get", "/v1/payments/00000000-0000-0000-0000-000000000000/receipt.pdf"),
    ],
)
def test_compras_no_ve_ni_registra_pagos(api: Api, method: str, path: str) -> None:  # noqa: F811
    api.client.app.dependency_overrides[get_current_user] = signed_in_as(  # type: ignore[attr-defined]
        Role.PURCHASING_MANAGER
    )

    response = getattr(api.client, method)(path, **({"json": {}} if method == "post" else {}))

    assert (response.status_code, response.json()["code"]) == (403, "auth.forbidden")
