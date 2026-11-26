"""Consultas que otros módulos usan por `inventory.public_api` (purchasing, HU28 y HU29;
reporting, HU14)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from local_eventos.modules.inventory.application.ports.product_repository import (
    ProductFilters,
    ProductRepository,
)
from local_eventos.modules.inventory.application.ports.stock_repository import (
    MovementRepository,
    StockRepository,
)
from local_eventos.modules.inventory.application.use_cases.products import (
    MAX_PRODUCTS,
    ListProducts,
    ProductViews,
)
from local_eventos.modules.inventory.domain.event_materials import EventMaterials
from local_eventos.modules.inventory.domain.movement import MovementKind
from local_eventos.modules.inventory.domain.product import Category, Product, ProductKind, Unit
from local_eventos.modules.inventory.domain.quantity import ZERO


@dataclass(frozen=True)
class ProductInfo:
    id: UUID
    code: str
    name: str
    unit: Unit
    kind: ProductKind
    active: bool


@dataclass(frozen=True)
class LowStockItem:
    """Producto activo bajo su mínimo y cuánto falta para volver a él (CA-28.2)."""

    product: ProductInfo
    stock: Decimal
    min_stock: Decimal
    shortage: Decimal


class LookupProduct:
    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    async def __call__(self, product_id: UUID) -> ProductInfo | None:
        product = await self._products.get(product_id)
        return None if product is None else _info(product)


class ListLowStock:
    def __init__(self, products: ProductRepository, stock: StockRepository) -> None:
        self._products = products
        self._stock = stock

    async def __call__(self) -> list[LowStockItem]:
        """Ordenados por nombre. Solo los que necesitan reponerse (stock menor al mínimo)."""
        products = await self._products.search(ProductFilters(), limit=MAX_PRODUCTS)
        levels = await self._stock.get_many([p.id for p in products])
        items = []
        for product in products:
            level = levels.get(product.id)
            quantity = level.quantity if level is not None else ZERO
            if quantity < product.min_stock:
                items.append(
                    LowStockItem(
                        product=_info(product),
                        stock=quantity,
                        min_stock=product.min_stock,
                        shortage=product.min_stock - quantity,
                    )
                )
        return items


@dataclass(frozen=True)
class EventMaterialInfo:
    """Por producto, qué salió, volvió, se perdió y falta devolver en un evento (CA-26.6)."""

    product: ProductInfo
    out: Decimal
    returned: Decimal
    wasted: Decimal
    pending_return: Decimal


class ListEventMaterials:
    """Materiales del evento para otros módulos (HU14). No revisa que el evento exista."""

    def __init__(self, products: ProductRepository, movements: MovementRepository) -> None:
        self._products = products
        self._movements = movements

    async def __call__(self, event_id: UUID) -> list[EventMaterialInfo]:
        movements = await self._movements.list_for_event(event_id)
        ids = list(dict.fromkeys(m.product_id for m in movements))
        lines = []
        for product in await self._products.get_many(ids):
            totals = EventMaterials.from_movements(product.id, product.kind, movements)
            lines.append(
                EventMaterialInfo(
                    product=_info(product),
                    out=totals.out,
                    returned=totals.returned,
                    wasted=totals.wasted,
                    pending_return=totals.pending_return,
                )
            )
        return sorted(lines, key=lambda line: line.product.name.lower())


def _info(product: Product) -> ProductInfo:
    return ProductInfo(
        id=product.id,
        code=product.code,
        name=product.name,
        unit=product.unit,
        kind=product.kind,
        active=product.active,
    )


@dataclass(frozen=True)
class StockItem:
    """Stock actual de un producto con sus alertas (reporte de almacén, CA-32.3)."""

    product: ProductInfo
    category: Category
    min_stock: Decimal
    stock: Decimal
    avg_cost_cents: int
    value_cents: int
    is_low_stock: bool
    next_expiry: date | None
    expiring_soon: bool


class ListStock:
    """Productos con su stock y alertas, ordenados por nombre (mismo cálculo que HU23)."""

    def __init__(self, products: ProductRepository, views: ProductViews) -> None:
        self._list = ListProducts(products, views)

    async def __call__(
        self, category: Category | None = None, *, include_inactive: bool = False
    ) -> list[StockItem]:
        views = await self._list(
            ProductFilters(category=category, include_inactive=include_inactive)
        )
        return [
            StockItem(
                product=_info(v.product),
                category=v.product.category,
                min_stock=v.product.min_stock,
                stock=v.stock,
                avg_cost_cents=v.avg_cost_cents,
                value_cents=v.stock_value_cents,
                is_low_stock=v.is_low_stock,
                next_expiry=v.next_expiry,
                expiring_soon=v.expiring_soon,
            )
            for v in views
        ]


@dataclass(frozen=True)
class MovementItem:
    """Un movimiento de almacén con su producto (reporte de movimientos, CA-32.3)."""

    occurred_on: date
    product: ProductInfo
    kind: MovementKind
    quantity: Decimal  # el ajuste lleva signo
    unit_cost_cents: int | None
    event_id: UUID | None
    lot: str | None
    reason: str | None


class ListMovementsBetween:
    def __init__(self, products: ProductRepository, movements: MovementRepository) -> None:
        self._products = products
        self._movements = movements

    async def __call__(
        self, date_from: date, date_to: date, kind: MovementKind | None = None
    ) -> list[MovementItem]:
        """Del más antiguo al más reciente."""
        movements = await self._movements.list_between(date_from, date_to, kind)
        ids = list(dict.fromkeys(m.product_id for m in movements))
        products = {p.id: _info(p) for p in await self._products.get_many(ids)}
        return [
            MovementItem(
                occurred_on=m.occurred_on,
                product=products[m.product_id],
                kind=m.kind,
                quantity=m.quantity,
                unit_cost_cents=m.unit_cost_cents,
                event_id=m.event_id,
                lot=m.lot,
                reason=m.reason,
            )
            for m in movements
            if m.product_id in products
        ]
