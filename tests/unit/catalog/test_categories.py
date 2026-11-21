"""Pruebas de los casos de uso de categorías (HU06). Sin base de datos."""

from uuid import uuid4

import pytest

from local_eventos.modules.catalog.application.errors import (
    CategoryNotFoundError,
    DuplicateCategoryNameError,
)
from local_eventos.modules.catalog.application.use_cases.change_category_status import (
    ActivateCategory,
    DeactivateCategory,
)
from local_eventos.modules.catalog.application.use_cases.create_category import (
    CreateCategory,
)
from local_eventos.modules.catalog.application.use_cases.list_categories import (
    ListCategories,
)
from local_eventos.modules.catalog.application.use_cases.rename_category import (
    RenameCategory,
)
from local_eventos.modules.catalog.domain.errors import CatalogValidationError

from .fakes import InMemoryCategoryRepository


@pytest.mark.asyncio
async def test_hu06_crea_y_guarda_la_categoria() -> None:
    repository = InMemoryCategoryRepository()

    category = await CreateCategory(repository)("Bebidas")

    assert repository.categories[category.id] is category


@pytest.mark.asyncio
async def test_hu06_rechaza_categoria_repetida_sin_importar_mayusculas() -> None:
    repository = InMemoryCategoryRepository()
    create = CreateCategory(repository)
    await create("Bebidas")

    with pytest.raises(DuplicateCategoryNameError) as error:
        await create("  BEBIDAS ")

    assert error.value.code == "catalog.category_name_duplicated"
    assert len(repository.categories) == 1


@pytest.mark.asyncio
async def test_hu06_categoria_invalida_no_se_guarda() -> None:
    repository = InMemoryCategoryRepository()

    with pytest.raises(CatalogValidationError):
        await CreateCategory(repository)("   ")

    assert repository.categories == {}


@pytest.mark.asyncio
async def test_hu06_renombra_la_categoria() -> None:
    repository = InMemoryCategoryRepository()
    category = await CreateCategory(repository)("Bebida")

    await RenameCategory(repository)(category.id, "Bebidas")

    assert repository.categories[category.id].name == "Bebidas"


@pytest.mark.asyncio
async def test_hu06_puede_cambiar_mayusculas_de_su_propio_nombre() -> None:
    repository = InMemoryCategoryRepository()
    category = await CreateCategory(repository)("bebidas")

    await RenameCategory(repository)(category.id, "Bebidas")

    assert category.name == "Bebidas"


@pytest.mark.asyncio
async def test_hu06_no_renombra_con_el_nombre_de_otra_categoria() -> None:
    repository = InMemoryCategoryRepository()
    create = CreateCategory(repository)
    await create("Bebidas")
    decoration = await create("Decoración")

    with pytest.raises(DuplicateCategoryNameError):
        await RenameCategory(repository)(decoration.id, "bebidas")


@pytest.mark.asyncio
async def test_hu06_categoria_inexistente() -> None:
    repository = InMemoryCategoryRepository()

    with pytest.raises(CategoryNotFoundError) as error:
        await RenameCategory(repository)(uuid4(), "Bebidas")
    assert error.value.code == "catalog.category_not_found"

    with pytest.raises(CategoryNotFoundError):
        await DeactivateCategory(repository)(uuid4())


@pytest.mark.asyncio
async def test_hu06_desactiva_y_reactiva_la_categoria() -> None:
    repository = InMemoryCategoryRepository()
    category = await CreateCategory(repository)("Decoración")

    await DeactivateCategory(repository)(category.id)
    assert repository.categories[category.id].active is False

    await ActivateCategory(repository)(category.id)
    assert repository.categories[category.id].active is True


@pytest.mark.asyncio
async def test_hu06_lista_solo_activas_por_defecto_y_ordenadas() -> None:
    repository = InMemoryCategoryRepository()
    create = CreateCategory(repository)
    await create("Mobiliario")
    await create("Bebidas")
    old = await create("Animación")
    await DeactivateCategory(repository)(old.id)
    list_categories = ListCategories(repository)

    active = await list_categories()
    everything = await list_categories(include_inactive=True)

    assert [c.name for c in active] == ["Bebidas", "Mobiliario"]
    assert [c.name for c in everything] == ["Animación", "Bebidas", "Mobiliario"]
