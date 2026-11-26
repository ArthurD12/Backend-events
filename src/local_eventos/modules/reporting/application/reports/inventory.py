"""Reportes de almacén (CA-32.3): stock actual por producto y movimientos por rango."""

from datetime import date
from decimal import Decimal

from local_eventos.modules.commercial.public_api import EventRefsLookup
from local_eventos.modules.inventory.public_api import (
    Category,
    MovementKind,
    MovementsReportLookup,
    StockReportLookup,
)
from local_eventos.modules.reporting.application.ports.clock import Clock
from local_eventos.modules.reporting.application.reports.labels import (
    MOVEMENT_KIND,
    PRODUCT_CATEGORY,
    UNIT,
)
from local_eventos.modules.reporting.application.reports.table import (
    Column,
    ColumnType,
    Filter,
    ReportTable,
    Total,
    check_range,
    range_filters,
)

STOCK_COLUMNS = (
    Column("code", "Código"),
    Column("product", "Producto"),
    Column("category", "Categoría"),
    Column("unit", "Unidad"),
    Column("stock", "Stock", ColumnType.QUANTITY),
    Column("min_stock", "Mínimo", ColumnType.QUANTITY),
    Column("avg_cost", "Costo promedio", ColumnType.MONEY),
    Column("value", "Valor", ColumnType.MONEY),
    Column("low_stock", "Stock bajo", ColumnType.BOOLEAN),
    Column("next_expiry", "Vence", ColumnType.DATE),
    Column("expiring_soon", "Por vencer", ColumnType.BOOLEAN),
    Column("active", "Activo", ColumnType.BOOLEAN),
)
MOVEMENT_COLUMNS = (
    Column("date", "Fecha", ColumnType.DATE),
    Column("code", "Código"),
    Column("product", "Producto"),
    Column("unit", "Unidad"),
    Column("kind", "Tipo"),
    Column("quantity", "Cantidad", ColumnType.QUANTITY),
    Column("unit_cost", "Costo unitario", ColumnType.MONEY),
    Column("event", "Evento"),
    Column("lot", "Lote"),
    Column("reason", "Motivo"),
)


class GetStockReport:
    def __init__(self, stock: StockReportLookup, clock: Clock) -> None:
        self._stock = stock
        self._clock = clock

    async def __call__(
        self, category: Category | None = None, *, include_inactive: bool = False
    ) -> ReportTable:
        items = await self._stock(category, include_inactive=include_inactive)
        filters = []
        if category is not None:
            filters.append(Filter("category", "Categoría", PRODUCT_CATEGORY[category]))
        if include_inactive:
            filters.append(Filter("include_inactive", "Incluye inactivos", "Sí"))
        return ReportTable(
            key="inventory",
            title="Reporte de almacén: stock actual",
            generated_at=self._clock.now(),
            filters=tuple(filters),
            columns=STOCK_COLUMNS,
            rows=tuple(
                (
                    i.product.code,
                    i.product.name,
                    PRODUCT_CATEGORY[i.category],
                    UNIT[i.product.unit],
                    i.stock,
                    i.min_stock,
                    i.avg_cost_cents,
                    i.value_cents,
                    i.is_low_stock,
                    i.next_expiry,
                    i.expiring_soon,
                    i.product.active,
                )
                for i in items
            ),
            totals=(
                Total("products", "Productos", ColumnType.INTEGER, len(items)),
                Total(
                    "value", "Valor del stock", ColumnType.MONEY, sum(i.value_cents for i in items)
                ),
                Total(
                    "low_stock",
                    "Con stock bajo",
                    ColumnType.INTEGER,
                    sum(1 for i in items if i.is_low_stock),
                ),
                Total(
                    "expiring_soon",
                    "Por vencer",
                    ColumnType.INTEGER,
                    sum(1 for i in items if i.expiring_soon),
                ),
            ),  # fmt: skip
        )


class GetInventoryMovementsReport:
    def __init__(
        self, movements: MovementsReportLookup, refs: EventRefsLookup, clock: Clock
    ) -> None:
        self._movements = movements
        self._refs = refs
        self._clock = clock

    async def __call__(
        self, date_from: date, date_to: date, kind: MovementKind | None = None
    ) -> ReportTable:
        check_range(date_from, date_to)
        items = await self._movements(date_from, date_to, kind)
        refs = await self._refs([i.event_id for i in items if i.event_id], [])
        filters = list(range_filters(date_from, date_to))
        if kind is not None:
            filters.append(Filter("kind", "Tipo", MOVEMENT_KIND[kind]))
        entries_value = sum(
            (i.quantity * i.unit_cost_cents for i in items
             if i.kind is MovementKind.ENTRY and i.unit_cost_cents is not None),
            Decimal(0),
        )  # fmt: skip
        return ReportTable(
            key="inventory_movements",
            title="Reporte de almacén: movimientos",
            generated_at=self._clock.now(),
            filters=tuple(filters),
            columns=MOVEMENT_COLUMNS,
            rows=tuple(
                (
                    i.occurred_on,
                    i.product.code,
                    i.product.name,
                    UNIT[i.product.unit],
                    MOVEMENT_KIND[i.kind],
                    i.quantity,
                    i.unit_cost_cents,
                    refs.by_event.get(i.event_id) if i.event_id else None,
                    i.lot,
                    i.reason,
                )
                for i in items
            ),
            totals=(
                Total("movements", "Movimientos", ColumnType.INTEGER, len(items)),
                Total(
                    "entries_value",
                    "Valor de las entradas",
                    ColumnType.MONEY,
                    int(entries_value.to_integral_value()),
                ),
            ),  # fmt: skip
        )
