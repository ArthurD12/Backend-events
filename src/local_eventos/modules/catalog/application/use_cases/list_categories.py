"""Caso de uso: listar categorías (HU06).

El formulario de servicios pide solo las activas; la pantalla del administrador, todas.
"""

from local_eventos.modules.catalog.application.ports.category_repository import (
    CategoryRepository,
)
from local_eventos.modules.catalog.domain.category import Category


class ListCategories:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    async def __call__(self, *, include_inactive: bool = False) -> list[Category]:
        return await self._categories.list(include_inactive=include_inactive)
