"""Casos de uso: desactivar y reactivar una categoría sin eliminarla (HU06, RN02).

No se desactiva una categoría con servicios activos (DOMAIN.md §4.1, regla 4).
"""

from uuid import UUID

from local_eventos.modules.catalog.application.errors import (
    CategoryHasActiveServicesError,
    CategoryNotFoundError,
)
from local_eventos.modules.catalog.application.ports.category_repository import (
    CategoryRepository,
)
from local_eventos.modules.catalog.application.ports.service_repository import (
    ServiceRepository,
)
from local_eventos.modules.catalog.domain.category import Category


class DeactivateCategory:
    def __init__(self, categories: CategoryRepository, services: ServiceRepository) -> None:
        self._categories = categories
        self._services = services

    async def __call__(self, category_id: UUID) -> Category:
        category = await _get_or_fail(self._categories, category_id)
        if await self._services.has_active_in_category(category_id):
            raise CategoryHasActiveServicesError()
        category.deactivate()
        await self._categories.update(category)
        return category


class ActivateCategory:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    async def __call__(self, category_id: UUID) -> Category:
        category = await _get_or_fail(self._categories, category_id)
        category.activate()
        await self._categories.update(category)
        return category


async def _get_or_fail(categories: CategoryRepository, category_id: UUID) -> Category:
    category = await categories.get(category_id)
    if category is None:
        raise CategoryNotFoundError()
    return category
