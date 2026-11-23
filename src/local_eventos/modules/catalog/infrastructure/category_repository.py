"""Repositorio de categorías en PostgreSQL (HU06): implementa el puerto `CategoryRepository`.

Traduce entre la entidad `Category` (reglas del negocio) y la fila `CategoryRow` (tabla).
No confirma la transacción: eso lo decide quien abre la sesión, una vez por petición.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.catalog.application.errors import DuplicateCategoryNameError
from local_eventos.modules.catalog.domain.category import Category
from local_eventos.modules.catalog.infrastructure.orm_models import CategoryRow


class SqlAlchemyCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, category_id: UUID) -> Category | None:
        row = await self._session.get(CategoryRow, category_id)
        return _to_category(row) if row is not None else None

    async def get_by_name(self, name: str) -> Category | None:
        row = await self._session.scalar(
            select(CategoryRow).where(func.lower(CategoryRow.name) == name.lower())
        )
        return _to_category(row) if row is not None else None

    async def add(self, category: Category) -> None:
        self._session.add(CategoryRow(id=category.id, name=category.name, active=category.active))
        await self._flush()

    async def update(self, category: Category) -> None:
        row = await self._session.get(CategoryRow, category.id)
        if row is None:
            raise LookupError(f"La categoría {category.id} no existe en la base de datos.")
        row.name = category.name
        row.active = category.active
        await self._flush()

    async def list(self, *, include_inactive: bool) -> list[Category]:
        query = select(CategoryRow)
        if not include_inactive:
            query = query.where(CategoryRow.active.is_(True))
        rows = await self._session.scalars(query.order_by(func.lower(CategoryRow.name)))
        return [_to_category(row) for row in rows]

    async def _flush(self) -> None:
        """Envía los cambios. Si el nombre ya existe, lo traduce a error de negocio.

        La aplicación ya revisa duplicados antes de guardar; esto cubre el caso en que dos
        personas crean la misma categoría al mismo tiempo (el índice único gana).
        """
        try:
            await self._session.flush()
        except IntegrityError as error:
            if "uq_catalog_categories_name_lower" in str(error.orig):
                raise DuplicateCategoryNameError() from error
            raise


def _to_category(row: CategoryRow) -> Category:
    return Category(id=row.id, name=row.name, active=row.active)
