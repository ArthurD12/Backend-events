"""Repositorios del catálogo en memoria para probar los casos de uso sin base de datos."""

from uuid import UUID

from local_eventos.modules.catalog.domain.category import Category
from local_eventos.modules.catalog.domain.service import Service


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


class InMemoryServiceRepository:
    def __init__(self) -> None:
        self.services: dict[UUID, Service] = {}

    async def get(self, service_id: UUID) -> Service | None:
        return self.services.get(service_id)

    async def add(self, service: Service) -> None:
        self.services[service.id] = service

    async def update(self, service: Service) -> None:
        self.services[service.id] = service

    async def search(
        self,
        text: str,
        *,
        category_id: UUID | None,
        active: bool | None,
        limit: int,
    ) -> list[Service]:
        needle = text.lower()
        found = [
            s
            for s in self.services.values()
            if needle in s.name.lower()
            and (category_id is None or s.category_id == category_id)
            and (active is None or s.active == active)
        ]
        return sorted(found, key=lambda s: s.name.lower())[:limit]
