"""Pruebas de los casos de uso de servicios (HU06). Sin base de datos."""

from uuid import UUID, uuid4

import pytest

from local_eventos.modules.catalog.application.errors import (
    CategoryInactiveError,
    CategoryNotFoundError,
    ServiceNotFoundError,
)
from local_eventos.modules.catalog.application.use_cases.change_service_status import (
    ActivateService,
    DeactivateService,
)
from local_eventos.modules.catalog.application.use_cases.register_service import (
    RegisterService,
    RegisterServiceCommand,
)
from local_eventos.modules.catalog.application.use_cases.search_services import (
    SearchServices,
    SearchServicesQuery,
)
from local_eventos.modules.catalog.application.use_cases.update_service import (
    UpdateService,
    UpdateServiceCommand,
)
from local_eventos.modules.catalog.domain.category import Category
from local_eventos.modules.catalog.domain.errors import CatalogValidationError
from local_eventos.modules.catalog.domain.service import PriceUnit, Service

from .fakes import InMemoryCategoryRepository, InMemoryServiceRepository


class Catalog:
    """Prepara los dos repositorios con una categoría activa: Comida."""

    def __init__(self) -> None:
        self.categories = InMemoryCategoryRepository()
        self.services = InMemoryServiceRepository()
        self.food = self.add_category("Comida")

    def add_category(self, name: str, *, active: bool = True) -> Category:
        category = Category.create(name=name)
        if not active:
            category.deactivate()
        self.categories.categories[category.id] = category
        return category

    async def register(
        self,
        name: str = "Buffet criollo",
        *,
        category_id: UUID | None = None,
        price_unit: PriceUnit = PriceUnit.PER_PERSON,
        price: int = 4500,
    ) -> Service:
        return await RegisterService(self.services, self.categories)(
            RegisterServiceCommand(
                name=name,
                category_id=category_id or self.food.id,
                price_unit=price_unit,
                reference_price_cents=price,
            )
        )

    async def update(
        self,
        service: Service,
        *,
        category_id: UUID | None = None,
        price: int | None = None,
    ) -> Service:
        """Modifica solo lo que se indica; el resto se envía con los valores actuales."""
        return await UpdateService(self.services, self.categories)(
            UpdateServiceCommand(
                service_id=service.id,
                name=service.name,
                category_id=category_id or service.category_id,
                price_unit=service.price_unit,
                reference_price_cents=(
                    service.reference_price_cents if price is None else price
                ),
            )
        )


@pytest.mark.asyncio
async def test_hu06_registra_y_guarda_el_servicio() -> None:
    catalog = Catalog()

    service = await catalog.register()

    assert catalog.services.services[service.id] is service
    assert service.active is True


@pytest.mark.asyncio
async def test_hu06_no_registra_en_categoria_inexistente() -> None:
    catalog = Catalog()

    with pytest.raises(CategoryNotFoundError):
        await catalog.register(category_id=uuid4())

    assert catalog.services.services == {}


@pytest.mark.asyncio
async def test_hu06_no_registra_en_categoria_desactivada() -> None:
    catalog = Catalog()
    old = catalog.add_category("Animación", active=False)

    with pytest.raises(CategoryInactiveError) as error:
        await catalog.register("Show de payasos", category_id=old.id)

    assert error.value.code == "catalog.category_inactive"
    assert catalog.services.services == {}


@pytest.mark.asyncio
async def test_hu06_servicio_invalido_no_se_guarda() -> None:
    catalog = Catalog()

    with pytest.raises(CatalogValidationError):
        await catalog.register(price=-1)

    assert catalog.services.services == {}


@pytest.mark.asyncio
async def test_hu06_modifica_precio_y_categoria() -> None:
    catalog = Catalog()
    furniture = catalog.add_category("Mobiliario")
    service = await catalog.register("Toldo 5x10", price_unit=PriceUnit.PER_UNIT)

    await catalog.update(service, category_id=furniture.id, price=35000)

    saved = catalog.services.services[service.id]
    assert saved.category_id == furniture.id
    assert saved.reference_price_cents == 35000


@pytest.mark.asyncio
async def test_hu06_no_mueve_un_servicio_a_categoria_desactivada() -> None:
    catalog = Catalog()
    old = catalog.add_category("Animación", active=False)
    service = await catalog.register()

    with pytest.raises(CategoryInactiveError):
        await catalog.update(service, category_id=old.id)

    assert service.category_id == catalog.food.id


@pytest.mark.asyncio
async def test_hu06_modifica_precio_aunque_su_categoria_este_desactivada() -> None:
    catalog = Catalog()
    service = await catalog.register()
    catalog.food.deactivate()

    await catalog.update(service, price=5000)

    assert service.reference_price_cents == 5000


@pytest.mark.asyncio
async def test_hu06_servicio_inexistente() -> None:
    catalog = Catalog()
    ghost = Service.register(
        name="Fantasma",
        category_id=catalog.food.id,
        price_unit=PriceUnit.PER_UNIT,
        reference_price_cents=100,
    )

    with pytest.raises(ServiceNotFoundError) as error:
        await catalog.update(ghost)
    assert error.value.code == "catalog.service_not_found"

    with pytest.raises(ServiceNotFoundError):
        await DeactivateService(catalog.services)(uuid4())


@pytest.mark.asyncio
async def test_hu06_desactiva_y_reactiva_el_servicio() -> None:
    catalog = Catalog()
    service = await catalog.register()

    await DeactivateService(catalog.services)(service.id)
    assert catalog.services.services[service.id].active is False

    await ActivateService(catalog.services)(service.id)
    assert catalog.services.services[service.id].active is True


@pytest.mark.asyncio
async def test_hu06_busca_por_nombre_categoria_y_estado() -> None:
    catalog = Catalog()
    drinks = catalog.add_category("Bebidas")
    await catalog.register("Buffet criollo")
    await catalog.register("Buffet marino")
    await catalog.register("Barra libre", category_id=drinks.id)
    old = await catalog.register("Buffet chifa")
    await DeactivateService(catalog.services)(old.id)
    search = SearchServices(catalog.services)

    by_name = await search(SearchServicesQuery(text="  BUFFET "))
    by_category = await search(SearchServicesQuery(category_id=drinks.id))
    inactive = await search(SearchServicesQuery(active=False))
    everything = await search(SearchServicesQuery(active=None))

    assert [s.name for s in by_name] == ["Buffet criollo", "Buffet marino"]
    assert [s.name for s in by_category] == ["Barra libre"]
    assert [s.name for s in inactive] == ["Buffet chifa"]
    assert len(everything) == 4
