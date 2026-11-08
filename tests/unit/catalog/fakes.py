"""Repositorios del catálogo en memoria para probar los casos de uso sin base de datos."""

from uuid import UUID

from local_eventos.modules.catalog.domain.category import Category


class InMemoryCategoryRepository:
    def __init__(self) -> None:
        self.categories: dict[UUID, Category] = {}

    async def get(self, category_id: UUID) -> Category | None:
        return self.categories.get(category_id)

    async def get_by_name(self, name: str) -> Category | None:
        wanted = name.lower()
        return next(
            (c for c in self.categories.values() if c.name.lower() == wanted), None
        )

    async def add(self, category: Category) -> None:
        self.categories[category.id] = category

    async def update(self, category: Category) -> None:
        self.categories[category.id] = category

    async def list(self, *, include_inactive: bool) -> list[Category]:
        found = [c for c in self.categories.values() if include_inactive or c.active]
        return sorted(found, key=lambda c: c.name.lower())
