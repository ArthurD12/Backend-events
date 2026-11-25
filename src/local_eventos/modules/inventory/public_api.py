"""Superficie pública del módulo inventory: única vía de uso por otros módulos.

`purchasing` consulta productos y faltantes, y registra las entradas al recibir una compra
dentro de la misma transacción de la petición; `reporting` lee los materiales de un evento
(AGENTS.md, regla 3).
"""

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.inventory import composition
from local_eventos.modules.inventory.application.use_cases.lookups import (
    EventMaterialInfo,
    ListEventMaterials,
    ListLowStock,
    LookupProduct,
    LowStockItem,
    ProductInfo,
)
from local_eventos.modules.inventory.application.use_cases.movements import (
    RecordedMovement,
    RecordEntries,
    StockEntry,
)
from local_eventos.modules.inventory.domain.errors import (
    InsufficientStockError,
    InventoryRuleError,
    InventoryValidationError,
)
from local_eventos.modules.inventory.domain.product import ProductKind, Unit


class ProductLookup(Protocol):
    """Busca un producto por su ID. `None` si no existe."""

    async def __call__(self, product_id: UUID) -> ProductInfo | None: ...


class LowStockLookup(Protocol):
    """Productos activos con stock menor al mínimo y cuánto falta (HU28)."""

    async def __call__(self) -> list[LowStockItem]: ...


class EventMaterialsLookup(Protocol):
    """Materiales de un evento por producto: salió, volvió, merma y falta devolver (HU14)."""

    async def __call__(self, event_id: UUID) -> list[EventMaterialInfo]: ...


class StockReceiver(Protocol):
    """Registra entradas de almacén (una por línea recibida) en la misma transacción."""

    async def __call__(
        self, entries: list[StockEntry], *, recorded_by: UUID
    ) -> list[RecordedMovement]: ...


def product_lookup(session: AsyncSession) -> ProductLookup:
    return LookupProduct(composition.product_repository(session))


def low_stock_lookup(session: AsyncSession) -> LowStockLookup:
    return ListLowStock(
        composition.product_repository(session), composition.stock_repository(session)
    )


def event_materials(session: AsyncSession) -> EventMaterialsLookup:
    """Consulta de solo lectura para la ficha del evento (HU14)."""
    return ListEventMaterials(
        composition.product_repository(session), composition.movement_repository(session)
    )


def stock_receiver(session: AsyncSession) -> StockReceiver:
    return RecordEntries(composition.record_movement(session))


__all__ = [
    "EventMaterialInfo",
    "EventMaterialsLookup",
    "InsufficientStockError",
    "InventoryRuleError",
    "InventoryValidationError",
    "LowStockItem",
    "LowStockLookup",
    "ProductInfo",
    "ProductKind",
    "ProductLookup",
    "RecordedMovement",
    "StockEntry",
    "StockReceiver",
    "Unit",
    "event_materials",
    "low_stock_lookup",
    "product_lookup",
    "stock_receiver",
]
