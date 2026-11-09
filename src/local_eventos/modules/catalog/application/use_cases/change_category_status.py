"""Casos de uso: desactivar y reactivar una categoría sin eliminarla (HU06, RN02)."""

from uuid import UUID

from local_eventos.modules.catalog.application.errors import CategoryNotFoundError
from local_eventos.modules.catalog.application.ports.category_repository import (
    CategoryRepository,
)
from local_eventos.modules.catalog.domain.category import Category


class DeactivateCategory:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    async def __call__(self, category_id: UUID) -> Category:
        category = await _get_or_fail(self._categories, category_id)
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
