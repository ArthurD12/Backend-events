"""Reporte de eventos (CA-32.1): por rango de fechas del evento, estado y cliente.

Los montos (total contratado, pagado y saldo) solo se muestran a quien puede ver los pagos
(`payments:record`); a los demás les llegan vacíos, en pantalla y en las descargas.
"""

from datetime import date
from uuid import UUID

from local_eventos.modules.commercial.public_api import (
    EventReportFilters,
    EventReportLookup,
    EventStatus,
)
from local_eventos.modules.reporting.application.ports.clock import Clock
from local_eventos.modules.reporting.application.reports.labels import EVENT_STATUS, EVENT_TYPE
from local_eventos.modules.reporting.application.reports.table import (
    Cell,
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
    Column("event_date", "Fecha", ColumnType.DATE),
    Column("client", "Cliente"),
    Column("event_type", "Tipo"),
    Column("guests", "Invitados", ColumnType.INTEGER),
    Column("status", "Estado"),
    Column("total", "Total contratado", ColumnType.MONEY),
    Column("paid", "Pagado", ColumnType.MONEY),
    Column("balance", "Saldo", ColumnType.MONEY),
)
HIDDEN_AMOUNTS = "Los montos se muestran solo a quien puede ver los pagos."


class GetEventsReport:
    def __init__(self, events: EventReportLookup, clock: Clock) -> None:
        self._events = events
        self._clock = clock

    async def __call__(
        self,
        date_from: date,
        date_to: date,
        *,
        status: EventStatus | None = None,
        client_id: UUID | None = None,
        include_amounts: bool,
    ) -> ReportTable:
        check_range(date_from, date_to)
        items = await self._events(
            EventReportFilters(
                date_from=date_from, date_to=date_to, status=status, client_id=client_id
            )
        )
        filters = list(range_filters(date_from, date_to))
        if status is not None:
            filters.append(Filter("status", "Estado", EVENT_STATUS[status]))
        if client_id is not None:
            name = items[0].client_name if items else "Sin eventos en el rango"
            filters.append(Filter("client", "Cliente", name))
        rows: list[tuple[Cell, ...]] = []
        for i in items:
            amounts: tuple[Cell, ...] = (
                (i.total_cents, i.paid_cents, i.balance_cents)
                if include_amounts
                else (None, None, None)
            )
            rows.append(
                (
                    i.code,
                    i.event_date,
                    i.client_name,
                    EVENT_TYPE[i.event_type],
                    i.guests,
                    EVENT_STATUS[i.status],
                    *amounts,
                )
            )

        def money(cents: int) -> int | None:
            return cents if include_amounts else None

        return ReportTable(
            key="events",
            title="Reporte de eventos",
            generated_at=self._clock.now(),
            filters=tuple(filters),
            columns=COLUMNS,
            rows=tuple(rows),
            totals=(
                Total("events", "Eventos", ColumnType.INTEGER, len(items)),
                Total("guests", "Invitados", ColumnType.INTEGER, sum(i.guests for i in items)),
                Total(
                    "total",
                    "Total contratado",
                    ColumnType.MONEY,
                    money(sum(i.total_cents for i in items)),
                ),
                Total("paid", "Pagado", ColumnType.MONEY, money(sum(i.paid_cents for i in items))),
                Total(
                    "balance",
                    "Saldo por cobrar",
                    ColumnType.MONEY,
                    money(sum(i.balance_cents for i in items)),
                ),
            ),  # fmt: skip
            notes=() if include_amounts else (HIDDEN_AMOUNTS,),
        )
