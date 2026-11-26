"""Requerimiento de materiales del evento (HU25, 021) con piezas en memoria."""

from typing import Any
from uuid import uuid4

from local_eventos.modules.commercial.public_api import EventStatus

from .test_inventory_api import Api, api  # noqa: F401


def _recipe(api: Api, service_id: Any, *lines: tuple[str, str, str]) -> None:  # noqa: F811
    response = api.client.put(
        f"/v1/inventory/recipes/{service_id}",
        json={"lines": [{"product_id": p, "quantity": q, "basis": b} for p, q, b in lines]},
    )
    assert response.status_code == 200, response.text


def _stock(api: Api, product_id: str, quantity: str) -> None:  # noqa: F811
    response = api.move("entry", product_id=product_id, quantity=quantity, unit_cost_cents=100)
    assert response.status_code == 201, response.text


def _lines(api: Api, event_id: Any) -> dict[str, dict[str, Any]]:  # noqa: F811
    response = api.client.get(f"/v1/inventory/events/{event_id}/requirement")
    assert response.status_code == 200, response.text
    return {line["code"]: line for line in response.json()["lines"]}


def test_ca25_1_y_ca25_2_requerido_salido_reservado_disponible_y_faltante(api: Api) -> None:  # noqa: F811
    menu, bar = api.services.add("Menú"), api.services.add("Barra")
    rice = api.product("ARR-01", name="Arroz", unit="KG", kind="CONSUMABLE")["id"]
    glass = api.product("COP-01", name="Copa", unit="UNIT")["id"]
    _recipe(api, menu, (rice, "0.15", "PER_PERSON"))
    _recipe(api, bar, (glass, "2", "PER_SERVICE"), (rice, "1", "PER_SERVICE"))
    event_id = api.event([(menu, 100), (bar, 3)], guests=100)
    api.events.events[event_id] = (
        api.events.events.get(event_id) or api.events.events[api.events.add()]
    )
    _stock(api, rice, "10")

    lines = _lines(api, event_id)

    # arroz: 0.15 × 100 invitados + 1 × 3 barras = 18; hay 10 → faltan 8
    assert lines["ARR-01"]["required"] == "18.000"
    assert lines["ARR-01"]["available"] == "10.000"
    assert lines["ARR-01"]["shortage"] == "8.000"
    # copas: 2 × 3 = 6; no hay stock
    assert lines["COP-01"]["required"] == "6.000"
    assert lines["COP-01"]["shortage"] == "6.000"


def test_faltante_nunca_es_negativo_si_sobra_stock(api: Api) -> None:  # noqa: F811
    menu = api.services.add()
    rice = api.product("ARR-01", name="Arroz", unit="KG", kind="CONSUMABLE")["id"]
    _recipe(api, menu, (rice, "0.1", "PER_PERSON"))
    event_id = api.event([(menu, 50)], guests=50)
    _stock(api, rice, "500")

    line = _lines(api, event_id)["ARR-01"]

    assert line["required"] == "5.000"
    assert line["shortage"] == "0.000"


def test_ca25_3_servicios_sin_receta_se_listan_aparte_y_los_extras_se_ignoran(api: Api) -> None:  # noqa: F811
    with_recipe, without = api.services.add("Menú"), api.services.add("Torta")
    rice = api.product("ARR-01", name="Arroz", unit="KG", kind="CONSUMABLE")["id"]
    _recipe(api, with_recipe, (rice, "0.1", "PER_PERSON"))
    event_id = api.event([(with_recipe, 10), (without, 1), (None, 1)], guests=10)

    body = api.client.get(f"/v1/inventory/events/{event_id}/requirement").json()

    assert body["without_recipe"] == ["Servicio 2"]
    assert [line["code"] for line in body["lines"]] == ["ARR-01"]
    assert body["calculated"] is True


def test_r_rec_2_evento_finalizado_no_se_calcula(api: Api) -> None:  # noqa: F811
    menu = api.services.add()
    rice = api.product("ARR-01", name="Arroz")["id"]
    _recipe(api, menu, (rice, "0.1", "PER_PERSON"))
    event_id = api.event([(menu, 10)], status=EventStatus.FINISHED)

    body = api.client.get(f"/v1/inventory/events/{event_id}/requirement").json()

    assert body["calculated"] is False
    assert body["lines"] == []


def test_lo_que_ya_salio_al_evento_baja_el_faltante(api: Api) -> None:  # noqa: F811
    menu = api.services.add()
    rice = api.product("ARR-01", name="Arroz", unit="KG", kind="CONSUMABLE")["id"]
    _recipe(api, menu, (rice, "0.1", "PER_PERSON"))
    event_id = api.events.add()
    api.details.events[event_id] = (
        api.details.events.get(event_id) or api.details.events[api.event([(menu, 100)], guests=100)]
    )
    _stock(api, rice, "6")
    api.move("exit", product_id=rice, quantity="4", event_id=str(event_id))

    line = _lines(api, event_id)["ARR-01"]

    assert (line["required"], line["out"], line["available"], line["shortage"]) == (
        "10.000",
        "4.000",
        "2.000",
        "4.000",
    )


def test_evento_inexistente_responde_404(api: Api) -> None:  # noqa: F811
    response = api.client.get(f"/v1/inventory/events/{uuid4()}/requirement")

    assert response.status_code == 404
    assert response.json()["code"] == "inventory.event_not_found"
