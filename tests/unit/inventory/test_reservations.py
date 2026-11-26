"""Reservas de materiales para un evento (HU25, CA-25.4 y CA-25.5, 021)."""

from typing import Any
from uuid import UUID

from local_eventos.modules.commercial.public_api import EventStatus
from local_eventos.modules.inventory.domain.reservation import ReservationStatus

from .test_inventory_api import Api, api  # noqa: F401
from .test_requirement import _lines, _recipe, _stock


def _reserve(api: Api, event_id: UUID, product_id: str, quantity: str) -> Any:  # noqa: F811
    return api.client.post(
        f"/v1/inventory/events/{event_id}/reservations",
        json={"lines": [{"product_id": product_id, "quantity": quantity}]},
    )


def _rice(api: Api) -> str:  # noqa: F811
    return api.product("ARR-01", name="Arroz", unit="KG", kind="CONSUMABLE")["id"]


def test_ca25_4_reservar_aparta_sin_mover_el_stock_y_se_suma(api: Api) -> None:  # noqa: F811
    rice = _rice(api)
    event_id = api.event([])
    _stock(api, rice, "10")

    first = _reserve(api, event_id, rice, "4")
    second = _reserve(api, event_id, rice, "1.5")
    product = api.client.get(f"/v1/inventory/products/{rice}").json()

    assert first.status_code == 201
    assert second.json()[0]["quantity"] == "5.500"
    assert product["stock"] == "10.000"  # R-REC-3: solo se aparta


def test_ca25_4_no_se_reserva_mas_de_lo_disponible_para_otros(api: Api) -> None:  # noqa: F811
    rice = _rice(api)
    first, second = api.event([]), api.event([])
    _stock(api, rice, "10")
    _reserve(api, first, rice, "7")

    too_much = _reserve(api, second, rice, "3.001")
    exact = _reserve(api, second, rice, "3")

    assert too_much.status_code == 409
    assert too_much.json()["code"] == "inventory.insufficient_available"
    assert exact.status_code == 201


def test_requerimiento_muestra_reservado_y_descuenta_del_faltante(api: Api) -> None:  # noqa: F811
    menu = api.services.add()
    rice = _rice(api)
    _recipe(api, menu, (rice, "0.1", "PER_PERSON"))
    event_id = api.event([(menu, 100)], guests=100)
    other = api.event([])
    _stock(api, rice, "8")
    _reserve(api, event_id, rice, "5")
    _reserve(api, other, rice, "2")

    line = _lines(api, event_id)["ARR-01"]

    # requerido 10; reservado 5; libre 8 - 7 = 1 → faltan 4
    assert (line["reserved"], line["available"], line["shortage"]) == (
        "5.000",
        "1.000",
        "4.000",
    )


def test_ca25_5_la_salida_consume_primero_la_reserva_del_evento(api: Api) -> None:  # noqa: F811
    rice = _rice(api)
    event_id, other = api.event([]), api.event([])
    _stock(api, rice, "10")
    _reserve(api, event_id, rice, "6")
    _reserve(api, other, rice, "3")

    exit_ = api.move("exit", product_id=rice, quantity="6", event_id=str(event_id))
    again = api.move("exit", product_id=rice, quantity="2", event_id=str(event_id))
    stock = api.client.get(f"/v1/inventory/products/{rice}").json()["stock"]

    assert exit_.status_code == 201  # sale lo reservado para él aunque otros tengan apartado
    assert again.status_code == 409  # quedan 4 en almacén y 3 son del otro evento: libre = 1
    assert again.json()["code"] == "inventory.insufficient_stock"
    assert stock == "4.000"
    # la reserva se consumió por completo
    assert api.client.get(f"/v1/inventory/events/{event_id}/requirement").status_code == 200


def test_la_salida_a_otro_evento_no_toca_lo_reservado(api: Api) -> None:  # noqa: F811
    rice = _rice(api)
    owner, other = api.event([]), api.event([])
    _stock(api, rice, "10")
    _reserve(api, owner, rice, "8")

    blocked = api.move("exit", product_id=rice, quantity="3", event_id=str(other))
    allowed = api.move("exit", product_id=rice, quantity="2", event_id=str(other))
    waste = api.move("waste", product_id=rice, quantity="1", reason="Se cayó")

    assert blocked.status_code == 409
    assert "solo hay 2" in blocked.json()["detail"]
    assert allowed.status_code == 201
    assert waste.status_code == 409  # el almacén ya no tiene libre


def test_salida_parcial_deja_el_resto_reservado(api: Api) -> None:  # noqa: F811
    menu = api.services.add()
    rice = _rice(api)
    _recipe(api, menu, (rice, "0.1", "PER_PERSON"))
    event_id = api.event([(menu, 100)], guests=100)
    _stock(api, rice, "10")
    _reserve(api, event_id, rice, "10")

    api.move("exit", product_id=rice, quantity="4", event_id=str(event_id))
    line = _lines(api, event_id)["ARR-01"]

    assert (line["out"], line["reserved"], line["available"], line["shortage"]) == (
        "4.000",
        "6.000",
        "0.000",
        "0.000",
    )


def test_eliminar_libera_la_reserva(api: Api) -> None:  # noqa: F811
    rice = _rice(api)
    event_id, other = api.event([]), api.event([])
    _stock(api, rice, "10")
    _reserve(api, event_id, rice, "10")

    removed = api.client.delete(f"/v1/inventory/events/{event_id}/reservations/{rice}")
    again = api.client.delete(f"/v1/inventory/events/{event_id}/reservations/{rice}")
    taken = _reserve(api, other, rice, "10")

    assert removed.status_code == 204
    assert again.status_code == 404
    assert again.json()["code"] == "inventory.reservation_not_found"
    assert taken.status_code == 201


def test_reservar_exige_evento_vigente_y_datos_validos(api: Api) -> None:  # noqa: F811
    rice = _rice(api)
    finished = api.event([], status=EventStatus.FINISHED)
    _stock(api, rice, "10")
    live = api.event([])

    on_finished = _reserve(api, finished, rice, "1")
    zero = _reserve(api, live, rice, "0")
    empty = api.client.post(f"/v1/inventory/events/{live}/reservations", json={"lines": []})
    unknown = _reserve(api, UUID(int=1), rice, "1")

    assert on_finished.json()["code"] == "inventory.event_not_assignable"
    assert zero.status_code == empty.status_code == 422
    assert unknown.json()["code"] == "inventory.event_not_found"


async def test_liberar_el_evento_deja_todo_disponible() -> None:
    from decimal import Decimal
    from uuid import uuid4

    from local_eventos.modules.inventory.application.use_cases.reservations import (
        ReleaseEventReservations,
    )
    from local_eventos.modules.inventory.domain.reservation import Reservation

    from .fakes import FakeClock, InMemoryReservationRepository

    repo, clock = InMemoryReservationRepository(), FakeClock()
    event_id, product_id, by = uuid4(), uuid4(), uuid4()
    await repo.save(
        Reservation.open(
            event_id=event_id, product_id=product_id, quantity=Decimal(3), by=by, now=clock.now()
        )
    )

    await ReleaseEventReservations(repo, clock)(event_id)

    assert await repo.active_totals([product_id]) == {}
    assert repo.reservations[0].status is ReservationStatus.RELEASED
