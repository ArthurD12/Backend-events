"""Puerto: cómo la aplicación guarda y lee categorías. La base de datos lo implementa."""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.catalog.domain.category import Category


class CategoryRepository(Protocol):
    async def get(self, category_id: UUID) -> Category | None: ...

    async def get_by_name(self, name: str) -> Category | None:
        """Busca por nombre exacto sin distinguir mayúsculas: "Bebidas" = "bebidas"."""
        ...

    async def add(self, category: Category) -> None: ...

    async def update(self, category: Category) -> None: ...

    async def list(self, *, include_inactive: bool) -> list[Category]:
        """Devuelve las categorías ordenadas por nombre."""
        ...
