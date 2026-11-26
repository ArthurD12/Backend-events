"""Puerto del repositorio de recetas (insumos por servicio)."""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.inventory.domain.recipe import RecipeLine


class RecipeRepository(Protocol):
    async def get(self, service_id: UUID) -> list[RecipeLine]: ...

    async def get_many(self, service_ids: list[UUID]) -> dict[UUID, list[RecipeLine]]:
        """Receta de cada servicio; los servicios sin receta no aparecen."""
        ...

    async def replace(self, service_id: UUID, lines: list[RecipeLine]) -> None:
        """Reemplaza toda la receta del servicio (CA-24.3)."""
        ...
