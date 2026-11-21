"""Caso de uso: renombrar una categoría sin repetir el nombre de otra (HU06)."""

from uuid import UUID

from local_eventos.modules.catalog.application.errors import (
    CategoryNotFoundError,
    DuplicateCategoryNameError,
)
from local_eventos.modules.catalog.application.ports.category_repository import (
    CategoryRepository,
)
from local_eventos.modules.catalog.domain.category import Category


class RenameCategory:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    async def __call__(self, category_id: UUID, name: str) -> Category:
        category = await self._categories.get(category_id)
        if category is None:
            raise CategoryNotFoundError()
        category.rename(name=name)
        other = await self._categories.get_by_name(category.name)
        if other is not None and other.id != category.id:
            raise DuplicateCategoryNameError()
        await self._categories.update(category)
        return category
