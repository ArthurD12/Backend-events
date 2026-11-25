"""Consultas que otros módulos usan por `inventory.public_api` (purchasing, HU28 y HU29)."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from local_eventos.modules.inventory.application.ports.product_repository import (
    ProductFilters,
    ProductRepository,
)
from local_eventos.modules.inventory.application.ports.stock_repository import StockRepository
from local_eventos.modules.inventory.application.use_cases.products import MAX_PRODUCTS
from local_eventos.modules.inventory.domain.product import ProductKind, Unit
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
        if product is None:
            return None
        return ProductInfo(
            id=product.id,
            code=product.code,
            name=product.name,
            unit=product.unit,
            kind=product.kind,
            active=product.active,
        )


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
                        product=ProductInfo(
                            id=product.id,
                            code=product.code,
                            name=product.name,
                            unit=product.unit,
                            kind=product.kind,
                            active=product.active,
                        ),
                        stock=quantity,
                        min_stock=product.min_stock,
                        shortage=product.min_stock - quantity,
                    )
                )
        return items
