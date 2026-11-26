"""Superficie pública del módulo inventory: única vía de uso por otros módulos.

`purchasing` consulta productos y faltantes, y registra las entradas al recibir una compra
dentro de la misma transacción de la petición; `reporting` lee los materiales de un evento
(AGENTS.md, regla 3).
"""

from datetime import date
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.inventory import composition
from local_eventos.modules.inventory.application.use_cases.lookups import (
    EventMaterialInfo,
    ListEventMaterials,
    ListLowStock,
    ListMovementsBetween,
    ListStock,
    LookupProduct,
    LowStockItem,
    MovementItem,
    ProductInfo,
    StockItem,
)
from local_eventos.modules.inventory.application.use_cases.movements import (
    RecordedMovement,
    RecordEntries,
    StockEntry,
)
from local_eventos.modules.inventory.application.use_cases.products import ProductViews
from local_eventos.modules.inventory.application.use_cases.requirement import (
    EventRequirement,
    GetEventRequirement,
    RequirementLine,
)
from local_eventos.modules.inventory.domain.errors import (
    InsufficientStockError,
    InventoryRuleError,
    InventoryValidationError,
)
from local_eventos.modules.inventory.domain.movement import MovementKind
from local_eventos.modules.inventory.domain.product import Category, ProductKind, Unit


class ProductLookup(Protocol):
    """Busca un producto por su ID. `None` si no existe."""

    async def __call__(self, product_id: UUID) -> ProductInfo | None: ...


class LowStockLookup(Protocol):
    """Productos activos con stock menor al mínimo y cuánto falta (HU28)."""

    async def __call__(self) -> list[LowStockItem]: ...


class EventMaterialsLookup(Protocol):
    """Materiales de un evento por producto: salió, volvió, merma y falta devolver (HU14)."""

    async def __call__(self, event_id: UUID) -> list[EventMaterialInfo]: ...


class EventRequirementLookup(Protocol):
    """Requerimiento del evento por producto y su faltante (HU25). `None` si no existe."""

    async def __call__(self, event_id: UUID) -> EventRequirement | None: ...


class StockReceiver(Protocol):
    """Registra entradas de almacén (una por línea recibida) en la misma transacción."""

    async def __call__(
        self, entries: list[StockEntry], *, recorded_by: UUID
    ) -> list[RecordedMovement]: ...


class StockReportLookup(Protocol):
    """Stock actual por producto con costo, valor y alertas (reporte de almacén y panel)."""

    async def __call__(
        self, category: Category | None = None, *, include_inactive: bool = False
    ) -> list[StockItem]: ...


class MovementsReportLookup(Protocol):
    """Movimientos de almacén del rango, con su producto (reporte de movimientos)."""

    async def __call__(
        self, date_from: date, date_to: date, kind: MovementKind | None = None
    ) -> list[MovementItem]: ...


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


def event_requirement(session: AsyncSession) -> EventRequirementLookup:
    """Cálculo al momento, solo lectura: `purchasing` arma la compra con los faltantes."""
    return GetEventRequirement(
        composition.event_details(session),
        composition.recipe_repository(session),
        composition.product_repository(session),
        composition.stock_repository(session),
        composition.movement_repository(session),
        composition.reservation_repository(session),
    )


def stock_receiver(session: AsyncSession) -> StockReceiver:
    return RecordEntries(composition.record_movement(session))


def stock_report(session: AsyncSession) -> StockReportLookup:
    """Consulta de solo lectura para `reporting` (CA-32.3, CA-31.10)."""
    views = ProductViews(
        composition.stock_repository(session),
        composition.movement_repository(session),
        composition.clock(),
    )
    return ListStock(composition.product_repository(session), views)


def movements_report(session: AsyncSession) -> MovementsReportLookup:
    """Consulta de solo lectura para `reporting` (CA-32.3)."""
    return ListMovementsBetween(
        composition.product_repository(session), composition.movement_repository(session)
    )


__all__ = [
    "Category",
    "EventMaterialInfo",
    "EventMaterialsLookup",
    "EventRequirement",
    "EventRequirementLookup",
    "InsufficientStockError",
    "InventoryRuleError",
    "InventoryValidationError",
    "LowStockItem",
    "LowStockLookup",
    "MovementItem",
    "MovementKind",
    "MovementsReportLookup",
    "ProductInfo",
    "ProductKind",
    "ProductLookup",
    "RecordedMovement",
    "RequirementLine",
    "StockEntry",
    "StockItem",
    "StockReceiver",
    "StockReportLookup",
    "Unit",
    "event_materials",
    "event_requirement",
    "low_stock_lookup",
    "movements_report",
    "product_lookup",
    "stock_receiver",
    "stock_report",
]
