"""Reporte de caja (CA-32.2): cada pago y movimiento del rango, con los anulados marcados.

Los totales no cuentan lo anulado y siguen el mismo cálculo que el flujo de caja (HU22):
saldo = pagos de clientes − devoluciones + otros ingresos − egresos. Solo administrador.
"""

from datetime import date

from local_eventos.modules.commercial.public_api import EventRefsLookup
from local_eventos.modules.ledger.public_api import CashEntriesLookup, CashEntry, CashEntryKind
from local_eventos.modules.reporting.application.ports.clock import Clock
from local_eventos.modules.reporting.application.reports.labels import (
    CASH_CATEGORY,
    CASH_KIND,
    PAYMENT_KIND,
)
from local_eventos.modules.reporting.application.reports.table import (
    Column,
    ColumnType,
    ReportTable,
    Total,
    check_range,
    range_filters,
)

COLUMNS = (
    Column("date", "Fecha", ColumnType.DATE),
    Column("type", "Tipo"),
    Column("category", "Categoría"),
    Column("concept", "Concepto"),
    Column("event", "Evento"),
    Column("amount", "Monto", ColumnType.MONEY),
    Column("voided", "Anulado", ColumnType.BOOLEAN),
)


class GetCashReport:
    def __init__(self, entries: CashEntriesLookup, refs: EventRefsLookup, clock: Clock) -> None:
        self._entries = entries
        self._refs = refs
        self._clock = clock

    async def __call__(self, date_from: date, date_to: date) -> ReportTable:
        check_range(date_from, date_to)
        entries = await self._entries(date_from, date_to)
        refs = await self._refs(
            [e.event_id for e in entries if e.event_id],
            [e.contract_id for e in entries if e.contract_id],
        )

        def event(entry: CashEntry) -> str | None:
            if entry.event_id is not None:
                return refs.by_event.get(entry.event_id)
            if entry.contract_id is not None:
                return refs.by_contract.get(entry.contract_id)
            return None

        def total(kind: CashEntryKind) -> int:
            return sum(e.amount_cents for e in entries if e.kind is kind and not e.voided)

        payments, refunds = total(CashEntryKind.CLIENT_PAYMENT), total(CashEntryKind.REFUND)
        income, expenses = total(CashEntryKind.INCOME), total(CashEntryKind.EXPENSE)
        money = ColumnType.MONEY
        return ReportTable(
            key="cash",
            title="Reporte de caja",
            generated_at=self._clock.now(),
            filters=range_filters(date_from, date_to),
            columns=COLUMNS,
            rows=tuple(
                (
                    e.occurred_on,
                    CASH_KIND[e.kind],
                    CASH_CATEGORY[e.category] if e.category else None,
                    f"{PAYMENT_KIND[e.payment_kind]} {e.concept}" if e.payment_kind else e.concept,
                    event(e),
                    e.amount_cents,
                    e.voided,
                )
                for e in entries
            ),
            totals=(
                Total("client_payments", "Pagos de clientes", money, payments),
                Total("refunds", "Devoluciones", money, refunds),
                Total("other_income", "Otros ingresos", money, income),
                Total(
                    "income", "Ingresos (netos de devoluciones)", money, payments - refunds + income
                ),
                Total("expenses", "Egresos", money, expenses),
                Total("net", "Saldo del periodo", money, payments - refunds + income - expenses),
            ),  # fmt: skip
            notes=("Los movimientos anulados se listan, pero no suman en los totales.",),
        )
