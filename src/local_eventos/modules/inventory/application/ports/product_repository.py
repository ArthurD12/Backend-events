"""Puerto del repositorio de productos."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from local_eventos.modules.inventory.domain.product import Category, Product


@dataclass(frozen=True)
class ProductFilters:
    text: str = ""  # parte del código o del nombre, sin distinguir tildes
    category: Category | None = None
    include_inactive: bool = False


class ProductRepository(Protocol):
    async def get(self, product_id: UUID) -> Product | None: ...

    async def get_many(self, product_ids: list[UUID]) -> list[Product]: ...

    async def get_by_code(self, code: str) -> Product | None: ...

    async def add(self, product: Product) -> None:
        """Si el código ya existe, lanza `CodeTakenError`."""
        ...

    async def update(self, product: Product) -> None: ...

    async def search(self, filters: ProductFilters, *, limit: int) -> list[Product]:
        """Productos que cumplen el filtro, ordenados por nombre."""
        ...
