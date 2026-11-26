"""Recetas en PostgreSQL: la receta de un servicio se reemplaza entera."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.inventory.domain.recipe import RecipeBasis, RecipeLine
from local_eventos.modules.inventory.infrastructure.orm_models import RecipeLineRow


class SqlAlchemyRecipeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, service_id: UUID) -> list[RecipeLine]:
        return (await self.get_many([service_id])).get(service_id, [])

    async def get_many(self, service_ids: list[UUID]) -> dict[UUID, list[RecipeLine]]:
        if not service_ids:
            return {}
        rows = await self._session.scalars(
            select(RecipeLineRow).where(RecipeLineRow.service_id.in_(service_ids))
        )
        found: dict[UUID, list[RecipeLine]] = {}
        for row in rows:
            found.setdefault(row.service_id, []).append(
                RecipeLine(row.product_id, row.quantity, RecipeBasis(row.basis))
            )
        return found

    async def replace(self, service_id: UUID, lines: list[RecipeLine]) -> None:
        await self._session.execute(
            delete(RecipeLineRow).where(RecipeLineRow.service_id == service_id)
        )
        self._session.add_all(
            RecipeLineRow(
                service_id=service_id,
                product_id=line.product_id,
                quantity=line.quantity,
                basis=line.basis.value,
            )
            for line in lines
        )
        await self._session.flush()
