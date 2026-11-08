"""Pruebas de la entidad Servicio (HU06). Sin base de datos."""

from typing import Any
from uuid import UUID, uuid4

import pytest

from local_eventos.modules.catalog.domain.errors import CatalogValidationError
from local_eventos.modules.catalog.domain.service import PriceUnit, Service

FOOD = UUID("00000000-0000-0000-0000-000000000001")


def _register(**overrides: Any) -> Service:
    data: dict[str, Any] = {
        "name": "Buffet criollo",
        "category_id": FOOD,
        "price_unit": PriceUnit.PER_PERSON,
        "reference_price_cents": 4500,
    }
    data.update(overrides)
    return Service.register(**data)


def test_hu06_registra_servicio_activo_con_datos_limpios() -> None:
    service = _register(name="  Buffet   criollo ", description="  Arroz con pato  ")

    assert service.active is True
    assert service.name == "Buffet criollo"
    assert service.description == "Arroz con pato"
    assert service.price_unit is PriceUnit.PER_PERSON
    assert service.reference_price_cents == 4500


def test_hu06_descripcion_es_opcional() -> None:
    assert _register(description=None).description is None
    assert _register(description="   ").description is None


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"name": "  "}, "catalog.service_name_required"),
        ({"name": "x" * 121}, "catalog.service_name_too_long"),
        ({"reference_price_cents": -1}, "catalog.price_invalid"),
        ({"reference_price_cents": 45.5}, "catalog.price_invalid"),
        ({"reference_price_cents": True}, "catalog.price_invalid"),
        ({"description": "x" * 501}, "catalog.description_too_long"),
    ],
)
def test_hu06_rechaza_datos_invalidos(overrides: dict[str, Any], code: str) -> None:
    with pytest.raises(CatalogValidationError) as error:
        _register(**overrides)

    assert error.value.code == code


def test_hu06_modifica_el_servicio() -> None:
    service = _register()
    other_category = uuid4()

    service.update(
        name="Toldo 5x10",
        category_id=other_category,
        price_unit=PriceUnit.PER_UNIT,
        reference_price_cents=35000,
    )

    assert service.name == "Toldo 5x10"
    assert service.category_id == other_category
    assert service.price_unit is PriceUnit.PER_UNIT
    assert service.reference_price_cents == 35000


def test_hu06_modificacion_invalida_no_cambia_nada() -> None:
    service = _register()

    with pytest.raises(CatalogValidationError):
        service.update(
            name="Otro nombre",
            category_id=uuid4(),
            price_unit=PriceUnit.PER_UNIT,
            reference_price_cents=-100,
        )

    assert service.name == "Buffet criollo"
    assert service.category_id == FOOD
    assert service.reference_price_cents == 4500


def test_hu06_desactivar_y_reactivar_servicio() -> None:
    service = _register()

    service.deactivate()
    assert service.active is False

    service.activate()
    assert service.active is True
