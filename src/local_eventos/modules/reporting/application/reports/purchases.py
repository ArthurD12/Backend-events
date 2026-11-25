"""Reporte de compras (CA-32.4): por rango de fecha de creación y estado."""

from datetime import date

from local_eventos.modules.commercial.public_api import EventRefsLookup
from local_eventos.modules.purchasing.public_api import PurchaseReportLookup, PurchaseStatus
from local_eventos.modules.reporting.application.ports.clock import Clock
from local_eventos.modules.reporting.application.reports.labels import PURCHASE_STATUS
from local_eventos.modules.reporting.application.reports.table import (
    Column,
    ColumnType,
    Filter,
    ReportTable,
    Total,
    check_range,
    range_filters,
)

COLUMNS = (
    Column("code", "Código"),
    Column("created_on", "Fecha", ColumnType.DATE),
    Column("supplier", "Proveedor"),
    Column("status", "Estado"),
    Column("event", "Evento"),
    Column("total", "Total", ColumnType.MONEY),
    Column("received_on", "Recepción", ColumnType.DATE),
)


class GetPurchasesReport:
    def __init__(
        self, purchases: PurchaseReportLookup, refs: EventRefsLookup, clock: Clock
    ) -> None:
        self._purchases = purchases
        self._refs = refs
        self._clock = clock

    async def __call__(
        self, date_from: date, date_to: date, status: PurchaseStatus | None = None
    ) -> ReportTable:
        check_range(date_from, date_to)
        items = await self._purchases(date_from, date_to, status)
        refs = await self._refs([i.event_id for i in items if i.event_id], [])
        filters = list(range_filters(date_from, date_to))
        if status is not None:
            filters.append(Filter("status", "Estado", PURCHASE_STATUS[status]))
        counted = [i for i in items if i.status is not PurchaseStatus.CANCELLED]
        return ReportTable(
            key="purchases",
            title="Reporte de compras",
            generated_at=self._clock.now(),
            filters=tuple(filters),
            columns=COLUMNS,
            rows=tuple(
                (
                    i.code,
                    i.created_on,
                    i.supplier_name,
                    PURCHASE_STATUS[i.status],
                    refs.by_event.get(i.event_id) if i.event_id else None,
                    i.total_cents,
                    i.received_on,
                )
                for i in items
            ),
            totals=(
                Total("purchases", "Compras", ColumnType.INTEGER, len(items)),
                Total(
                    "total",
                    "Total (sin canceladas)",
                    ColumnType.MONEY,
                    sum(i.total_cents or 0 for i in counted),
                ),
            ),  # fmt: skip
            notes=("Una compra solicitada aún no tiene costos: su total queda vacío.",),
        )
