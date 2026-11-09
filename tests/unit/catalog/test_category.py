"""Pruebas de la entidad Categoría (HU06). Sin base de datos."""

import pytest

from local_eventos.modules.catalog.domain.category import Category
from local_eventos.modules.catalog.domain.errors import CatalogValidationError


def test_hu06_crea_categoria_activa_con_nombre_limpio() -> None:
    category = Category.create(name="  Menaje   y vajilla ")

    assert category.name == "Menaje y vajilla"
    assert category.active is True


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("   ", "catalog.category_name_required"),
        ("x" * 61, "catalog.category_name_too_long"),
    ],
)
def test_hu06_rechaza_nombre_de_categoria_invalido(name: str, code: str) -> None:
    with pytest.raises(CatalogValidationError) as error:
        Category.create(name=name)

    assert error.value.code == code


def test_hu06_renombrar_invalido_conserva_el_nombre() -> None:
    category = Category.create(name="Bebidas")

    with pytest.raises(CatalogValidationError):
        category.rename(name="  ")

    assert category.name == "Bebidas"


def test_hu06_desactivar_y_reactivar_categoria() -> None:
    category = Category.create(name="Decoración")

    category.deactivate()
    assert category.active is False

    category.activate()
    assert category.active is True
