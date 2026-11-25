"""Consultas que otros módulos usan por `inventory.public_api` (purchasing, HU28 y HU29;
reporting, HU14)."""

from dataclasses import dataclass
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
from local_eventos.modules.inventory.application.use_cases.products import MAX_PRODUCTS
from local_eventos.modules.inventory.domain.event_materials import EventMaterials
from local_eventos.modules.inventory.domain.product import Product, ProductKind, Unit
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
