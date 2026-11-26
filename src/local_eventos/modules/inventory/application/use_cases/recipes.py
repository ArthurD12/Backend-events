"""Casos de uso de recetas (HU24): ver y reemplazar los insumos de un servicio."""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.catalog.public_api import ServiceLookup
from local_eventos.modules.inventory.application.errors import (
    ProductNotFoundError,
    ServiceNotFoundError,
)
from local_eventos.modules.inventory.application.ports.product_repository import (
    ProductRepository,
)
from local_eventos.modules.inventory.application.ports.recipe_repository import RecipeRepository
from local_eventos.modules.inventory.domain.product import Product
from local_eventos.modules.inventory.domain.recipe import RecipeLine, clean_recipe


@dataclass(frozen=True)
class RecipeView:
    service_id: UUID
    service_name: str
    lines: list[tuple[RecipeLine, Product]]


class _RecipeBuilder:
    def __init__(self, recipes: RecipeRepository, products: ProductRepository) -> None:
        self._recipes = recipes
        self._products = products

    async def view(self, service_id: UUID, name: str) -> RecipeView:
        lines = await self._recipes.get(service_id)
        found = {p.id: p for p in await self._products.get_many([ln.product_id for ln in lines])}
        items = [(ln, found[ln.product_id]) for ln in lines if ln.product_id in found]
        items.sort(key=lambda item: item[1].name.lower())
        return RecipeView(service_id, name, items)


class GetRecipe:
    def __init__(
        self, recipes: RecipeRepository, products: ProductRepository, services: ServiceLookup
    ) -> None:
        self._builder = _RecipeBuilder(recipes, products)
        self._services = services

    async def __call__(self, service_id: UUID) -> RecipeView:
        service = await self._services(service_id)
        if service is None:
            raise ServiceNotFoundError()
        return await self._builder.view(service_id, service.name)


class PutRecipe:
    def __init__(
        self, recipes: RecipeRepository, products: ProductRepository, services: ServiceLookup
    ) -> None:
        self._recipes = recipes
        self._products = products
        self._services = services
        self._builder = _RecipeBuilder(recipes, products)

    async def __call__(self, service_id: UUID, lines: list[RecipeLine]) -> RecipeView:
        """CA-24.1 a CA-24.3: valida y guarda todos los insumos en una sola operación."""
        service = await self._services(service_id)
        if service is None:
            raise ServiceNotFoundError()
        cleaned = clean_recipe(lines)
        found = {p.id for p in await self._products.get_many([ln.product_id for ln in cleaned])}
        if any(ln.product_id not in found for ln in cleaned):
            raise ProductNotFoundError()
        await self._recipes.replace(service_id, cleaned)
        return await self._builder.view(service_id, service.name)
