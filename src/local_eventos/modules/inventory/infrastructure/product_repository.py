"""Productos en PostgreSQL: implementa `ProductRepository`."""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.inventory.application.errors import CodeTakenError
from local_eventos.modules.inventory.application.ports.product_repository import ProductFilters
from local_eventos.modules.inventory.application.search_text import (
    WITH_ACCENTS,
    WITHOUT_ACCENTS,
    normalize,
)
from local_eventos.modules.inventory.domain.product import Category, Product, ProductKind, Unit
from local_eventos.modules.inventory.infrastructure.orm_models import ProductRow


class SqlAlchemyProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, product_id: UUID) -> Product | None:
        row = await self._session.get(ProductRow, product_id)
        return _to_product(row) if row is not None else None

    async def get_many(self, product_ids: list[UUID]) -> list[Product]:
        if not product_ids:
            return []
        rows = await self._session.scalars(select(ProductRow).where(ProductRow.id.in_(product_ids)))
        return [_to_product(row) for row in rows]

    async def get_by_code(self, code: str) -> Product | None:
        row = await self._session.scalar(select(ProductRow).where(ProductRow.code == code))
        return _to_product(row) if row is not None else None

    async def add(self, product: Product) -> None:
        row = ProductRow(id=product.id)
        _copy(product, row)
        self._session.add(row)
        await self._flush()

    async def update(self, product: Product) -> None:
        row = await self._session.get(ProductRow, product.id)
        if row is None:
            raise LookupError(f"El producto {product.id} no existe en la base de datos.")
        _copy(product, row)
        await self._flush()

    async def search(self, filters: ProductFilters, *, limit: int) -> list[Product]:
        query = select(ProductRow)
        if not filters.include_inactive:
            query = query.where(ProductRow.active.is_(True))
        if filters.category is not None:
            query = query.where(ProductRow.category == filters.category.value)
        if filters.text:
            name = func.translate(func.lower(ProductRow.name), WITH_ACCENTS, WITHOUT_ACCENTS)
            query = query.where(
                or_(
                    name.contains(normalize(filters.text), autoescape=True),
                    func.lower(ProductRow.code).contains(filters.text.lower(), autoescape=True),
                )
            )
        rows = await self._session.scalars(query.order_by(ProductRow.name).limit(limit))
        return [_to_product(row) for row in rows]

    async def _flush(self) -> None:
        """Dos personas registrando el mismo código a la vez: gana la restricción UNIQUE."""
        try:
            await self._session.flush()
        except IntegrityError as error:
            if "uq_inventory_products_code" in str(error.orig):
                raise CodeTakenError() from error
            raise


def _to_product(row: ProductRow) -> Product:
    return Product(
        id=row.id,
        code=row.code,
        name=row.name,
        category=Category(row.category),
        unit=Unit(row.unit),
        kind=ProductKind(row.kind),
        min_stock=row.min_stock,
        active=row.active,
    )


def _copy(product: Product, row: ProductRow) -> None:
    row.code = product.code
    row.name = product.name
    row.category = product.category.value
    row.unit = product.unit.value
    row.kind = product.kind.value
    row.min_stock = product.min_stock
    row.active = product.active
