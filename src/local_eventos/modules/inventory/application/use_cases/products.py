"""Casos de uso de productos (HU23): registrar, modificar, activar y consultar con alertas."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from uuid import UUID

from local_eventos.modules.inventory.application.errors import (
    CodeTakenError,
    ProductNotFoundError,
)
from local_eventos.modules.inventory.application.ports.clock import Clock
from local_eventos.modules.inventory.application.ports.product_repository import (
    ProductFilters,
    ProductRepository,
)
from local_eventos.modules.inventory.application.ports.stock_repository import (
    MovementRepository,
    StockRepository,
)
from local_eventos.modules.inventory.domain.movement import Movement
from local_eventos.modules.inventory.domain.product import (
    Category,
    Product,
    ProductKind,
    Unit,
)
from local_eventos.modules.inventory.domain.stock import (
    StockLevel,
    is_expiring_soon,
    is_low_stock,
    next_expiry,
)

MAX_PRODUCTS = 500  # una MYPE no llega a tantos productos
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class ProductCommand:
    code: str
    name: str
    category: Category
    unit: Unit
    kind: ProductKind
    min_stock: Decimal


@dataclass(frozen=True)
class ProductView:
    """Producto con su stock y sus alertas (CA-23.4, CA-23.5)."""

    product: Product
    stock: Decimal
    avg_cost_cents: int
    stock_value_cents: int
    is_low_stock: bool
    next_expiry: date | None
    expiring_soon: bool


@dataclass(frozen=True)
class MovementPage:
    items: list[Movement]
    total: int
    page: int
    page_size: int


class CreateProduct:
    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    async def __call__(self, command: ProductCommand) -> Product:
        product = Product.create(
            code=command.code,
            name=command.name,
            category=command.category,
            unit=command.unit,
            kind=command.kind,
            min_stock=command.min_stock,
        )
        if await self._products.get_by_code(product.code) is not None:
            raise CodeTakenError()
        await self._products.add(product)
        return product


class UpdateProduct:
    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    async def __call__(self, product_id: UUID, command: ProductCommand) -> Product:
        product = await _get(self._products, product_id)
        product.update(
            code=command.code,
            name=command.name,
            category=command.category,
            unit=command.unit,
            kind=command.kind,
            min_stock=command.min_stock,
        )
        same_code = await self._products.get_by_code(product.code)
        if same_code is not None and same_code.id != product.id:
            raise CodeTakenError()
        await self._products.update(product)
        return product


class SetProductActive:
    """CA-23.3: un producto no se elimina; se desactiva y se puede volver a activar."""

    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    async def __call__(self, product_id: UUID, *, active: bool) -> Product:
        product = await _get(self._products, product_id)
        if active:
            product.activate()
        else:
            product.deactivate()
        await self._products.update(product)
        return product


class ProductViews:
    """Arma la vista de stock y alertas de varios productos con pocas consultas."""

    def __init__(self, stock: StockRepository, movements: MovementRepository, clock: Clock) -> None:
        self._stock = stock
        self._movements = movements
        self._clock = clock

    async def __call__(self, products: list[Product]) -> list[ProductView]:
        ids = [p.id for p in products]
        levels = await self._stock.get_many(ids)
        entries = await self._movements.entries_for(ids)
        today = self._clock.today()
        views = []
        for product in products:
            level = levels.get(product.id, StockLevel(product.id))
            expiry = next_expiry(level.quantity, [e for e in entries if e.product_id == product.id])
            views.append(
                ProductView(
                    product=product,
                    stock=level.quantity,
                    avg_cost_cents=level.avg_cost_cents,
                    stock_value_cents=level.value_cents,
                    is_low_stock=is_low_stock(level.quantity, product.min_stock),
                    next_expiry=expiry,
                    expiring_soon=is_expiring_soon(expiry, today),
                )
            )
        return views


class ListProducts:
    def __init__(self, products: ProductRepository, views: ProductViews) -> None:
        self._products = products
        self._views = views

    async def __call__(
        self, filters: ProductFilters, *, alerts_only: bool = False
    ) -> list[ProductView]:
        """CA-23.5. `alerts_only` deja solo los de stock bajo o por vencer."""
        found = await self._products.search(
            replace(filters, text=" ".join(filters.text.split())), limit=MAX_PRODUCTS
        )
        views = await self._views(found)
        if alerts_only:
            views = [v for v in views if v.is_low_stock or v.expiring_soon]
        return views


class GetProduct:
    def __init__(self, products: ProductRepository, views: ProductViews) -> None:
        self._products = products
        self._views = views

    async def __call__(self, product_id: UUID) -> ProductView:
        product = await _get(self._products, product_id)
        return (await self._views([product]))[0]


class ListProductMovements:
    """CA-23.4: historial de movimientos del producto, del más reciente al más antiguo."""

    def __init__(self, products: ProductRepository, movements: MovementRepository) -> None:
        self._products = products
        self._movements = movements

    async def __call__(
        self, product_id: UUID, *, page: int = 1, page_size: int = 50
    ) -> MovementPage:
        await _get(self._products, product_id)
        page = max(page, 1)
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        items, total = await self._movements.list_for_product(
            product_id, limit=page_size, offset=(page - 1) * page_size
        )
        return MovementPage(items=items, total=total, page=page, page_size=page_size)


async def _get(products: ProductRepository, product_id: UUID) -> Product:
    product = await products.get(product_id)
    if product is None:
        raise ProductNotFoundError()
    return product
