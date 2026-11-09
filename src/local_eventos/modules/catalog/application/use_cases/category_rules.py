"""Regla compartida por registrar y modificar servicios (HU06)."""

from uuid import UUID

from local_eventos.modules.catalog.application.errors import (
    CategoryInactiveError,
    CategoryNotFoundError,
)
from local_eventos.modules.catalog.application.ports.category_repository import (
    CategoryRepository,
)


async def require_active_category(
    categories: CategoryRepository, category_id: UUID
) -> None:
    """Un servicio solo puede entrar a una categoría que existe y está activa."""
    category = await categories.get(category_id)
    if category is None:
        raise CategoryNotFoundError()
    if not category.active:
        raise CategoryInactiveError()
