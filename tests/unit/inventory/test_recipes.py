"""Recetas por servicio (HU24, 021) con piezas en memoria."""

from decimal import Decimal
from uuid import uuid4

from local_eventos.modules.inventory.domain.recipe import RecipeBasis, RecipeLine

from .test_inventory_api import Api, api  # noqa: F401


def _line(product_id: str, quantity: str = "0.150", basis: str = "PER_PERSON") -> dict[str, str]:
    return {"product_id": product_id, "quantity": quantity, "basis": basis}


def test_ca24_1_servicio_sin_receta_devuelve_lista_vacia(api: Api) -> None:  # noqa: F811
    service_id = api.services.add("Menú criollo")

    response = api.client.get(f"/v1/inventory/recipes/{service_id}")

    assert response.status_code == 200
    assert response.json() == {
        "service_id": str(service_id),
        "service_name": "Menú criollo",
        "lines": [],
    }


def test_ca24_1_y_ca24_3_guarda_y_reemplaza_todos_los_insumos(api: Api) -> None:  # noqa: F811
    service_id = api.services.add()
    rice = api.product("ARR-01", name="Arroz", unit="KG", kind="CONSUMABLE")["id"]
    glass = api.product("COP-01", name="Copa", unit="UNIT")["id"]

    first = api.client.put(
        f"/v1/inventory/recipes/{service_id}",
        json={"lines": [_line(rice, "0.15"), _line(glass, "1", "PER_SERVICE")]},
    )
    second = api.client.put(
        f"/v1/inventory/recipes/{service_id}", json={"lines": [_line(rice, "0.2")]}
    )
    again = api.client.get(f"/v1/inventory/recipes/{service_id}")

    assert first.status_code == 200
    assert [ln["name"] for ln in first.json()["lines"]] == ["Arroz", "Copa"]
    assert first.json()["lines"][0]["quantity"] == "0.150"
    assert first.json()["lines"][1]["basis"] == "PER_SERVICE"
    assert second.status_code == 200
    assert [ln["quantity"] for ln in again.json()["lines"]] == ["0.200"]


def test_ca24_2_un_producto_dos_veces_es_invalido(api: Api) -> None:  # noqa: F811
    service_id = api.services.add()
    rice = api.product("ARR-01", name="Arroz")["id"]

    response = api.client.put(
        f"/v1/inventory/recipes/{service_id}", json={"lines": [_line(rice), _line(rice, "2")]}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "inventory.validation"


def test_cantidad_cero_o_con_mas_de_3_decimales_es_invalida(api: Api) -> None:  # noqa: F811
    service_id = api.services.add()
    rice = api.product("ARR-01", name="Arroz")["id"]

    zero = api.client.put(f"/v1/inventory/recipes/{service_id}", json={"lines": [_line(rice, "0")]})
    many = api.client.put(
        f"/v1/inventory/recipes/{service_id}", json={"lines": [_line(rice, "0.1234")]}
    )

    assert zero.status_code == many.status_code == 422


def test_servicio_o_producto_inexistente_responde_404(api: Api) -> None:  # noqa: F811
    service_id = api.services.add()

    no_service = api.client.get(f"/v1/inventory/recipes/{uuid4()}")
    no_product = api.client.put(
        f"/v1/inventory/recipes/{service_id}", json={"lines": [_line(str(uuid4()))]}
    )

    assert no_service.json()["code"] == "inventory.service_not_found"
    assert no_product.json()["code"] == "inventory.product_not_found"


def test_por_persona_redondea_hacia_arriba_a_3_decimales() -> None:
    line = RecipeLine(uuid4(), Decimal("0.0333"), RecipeBasis.PER_PERSON)
    # 0.0333 no es una cantidad válida de receta, pero el cálculo igual redondea hacia arriba.
    assert line.required_for(guests=10, contracted=1) == Decimal("0.333")
    per_service = RecipeLine(uuid4(), Decimal("0.500"), RecipeBasis.PER_SERVICE)
    assert per_service.required_for(guests=80, contracted=3) == Decimal("1.500")
