"""Caso de uso: crear una categoría de servicios (HU06)."""

from local_eventos.modules.catalog.application.errors import DuplicateCategoryNameError
from local_eventos.modules.catalog.application.ports.category_repository import (
    CategoryRepository,
)
from local_eventos.modules.catalog.domain.category import Category


class CreateCategory:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    async def __call__(self, name: str) -> Category:
        category = Category.create(name=name)
        if await self._categories.get_by_name(category.name) is not None:
            raise DuplicateCategoryNameError()
        await self._categories.add(category)
        return category
