"""Forma de la respuesta del panel del administrador (HU31)."""

from datetime import date
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.commercial.public_api import (
    EventReportItem,
    QuoteStats,
    QuoteSummary,
    Receivables,
)
from local_eventos.modules.purchasing.public_api import OpenPurchases
from local_eventos.modules.reporting.application.use_cases.cash_flow import CashSummary
from local_eventos.modules.reporting.application.use_cases.get_dashboard import (
    Dashboard,
    InventoryAlerts,
)


class DashboardQuoteOut(BaseModel):
    id: UUID
    code: str
    client_name: str
    event_type: str
    event_date: date
    guests: int
    total_cents: int
    status: str

    @classmethod
    def from_summary(cls, summary: QuoteSummary) -> Self:
        return cls(
            id=summary.id,
            code=summary.code,
            client_name=summary.client_name,
            event_type=summary.event_type.value,
            event_date=summary.event_date,
            guests=summary.guests,
            total_cents=summary.total_cents,
            status=summary.status.value,
        )


class DashboardQuotesOut(BaseModel):
    drafts: int = Field(description="En borrador y vigentes")
    sent_pending: int = Field(description="Enviadas, vigentes, esperando respuesta")
    created_in_month: int
    accepted_in_month: int = Field(description="Creadas en el mes y hoy aceptadas")
    accepted_amount_cents: int
    upcoming: list[DashboardQuoteOut] = Field(
        description="Aceptadas con evento en los próximos 30 días. Obsoleto: usar "
        "`upcoming_events` del panel (CA-31.7)"
    )
    recent: list[DashboardQuoteOut]

    @classmethod
    def from_stats(cls, stats: QuoteStats) -> Self:
        return cls(
            drafts=stats.drafts,
            sent_pending=stats.sent_pending,
            created_in_month=stats.created_in_month,
            accepted_in_month=stats.accepted_in_month,
            accepted_amount_cents=stats.accepted_amount_cents,
            upcoming=[DashboardQuoteOut.from_summary(q) for q in stats.upcoming],
            recent=[DashboardQuoteOut.from_summary(q) for q in stats.recent],
        )


class DashboardEventOut(BaseModel):
    id: UUID
    code: str
    event_date: date
    client_name: str
    status: str
    balance_cents: int = Field(description="Saldo por cobrar del contrato (RN15)")
    overdue: bool = Field(description="Saldo vencido (R-PAG-2)")

    @classmethod
    def from_item(cls, item: EventReportItem) -> Self:
        return cls(
            id=item.id,
            code=item.code,
            event_date=item.event_date,
            client_name=item.client_name,
            status=item.status.value,
            balance_cents=item.balance_cents,
            overdue=item.overdue,
        )


class DashboardCashOut(BaseModel):
    """Caja del mes elegido, con el mismo cálculo que el flujo de caja (HU22)."""

    income_cents: int = Field(description="Pagos de clientes netos de devoluciones + otros")
    expense_cents: int
    net_cents: int

    @classmethod
    def from_summary(cls, summary: CashSummary) -> Self:
        return cls(
            income_cents=summary.income_cents,
            expense_cents=summary.expense_cents,
            net_cents=summary.net_cents,
        )


class DashboardReceivablesOut(BaseModel):
    total_cents: int = Field(description="Por cobrar de contratos firmados")
    contracts: int = Field(description="Contratos firmados con saldo")
    overdue_contracts: int = Field(description="De ellos, con el saldo vencido")
    overdue_cents: int

    @classmethod
    def from_receivables(cls, receivables: Receivables) -> Self:
        return cls(
            total_cents=receivables.total_cents,
            contracts=receivables.contracts,
            overdue_contracts=receivables.overdue_contracts,
            overdue_cents=receivables.overdue_cents,
        )


class DashboardInventoryOut(BaseModel):
    low_stock: int = Field(description="Productos activos en stock bajo")
    expiring_soon: int = Field(description="Productos activos por vencer (15 días o menos)")

    @classmethod
    def from_alerts(cls, alerts: InventoryAlerts) -> Self:
        return cls(low_stock=alerts.low_stock, expiring_soon=alerts.expiring_soon)


class DashboardPurchasesOut(BaseModel):
    requested: int
    ordered: int
    open: int = Field(description="Solicitadas + ordenadas")

    @classmethod
    def from_open(cls, purchases: OpenPurchases) -> Self:
        return cls(requested=purchases.requested, ordered=purchases.ordered, open=purchases.total)


class DashboardOut(BaseModel):
    month: str = Field(description="AAAA-MM")
    currency: str = "PEN"
    quotes: DashboardQuotesOut
    upcoming_events: list[DashboardEventOut] = Field(
        description="Eventos de hoy a 14 días, sin cancelados ni finalizados (CA-31.7)"
    )
    cash: DashboardCashOut = Field(description="Caja del mes elegido (CA-31.8)")
    receivables: DashboardReceivablesOut = Field(description="Cobros pendientes (CA-31.9)")
    inventory: DashboardInventoryOut = Field(description="Alertas de almacén (CA-31.10)")
    purchases: DashboardPurchasesOut = Field(description="Compras abiertas (CA-31.11)")

    @classmethod
    def from_dashboard(cls, dashboard: Dashboard) -> Self:
        return cls(
            month=f"{dashboard.year:04d}-{dashboard.month:02d}",
            quotes=DashboardQuotesOut.from_stats(dashboard.quotes),
            upcoming_events=[DashboardEventOut.from_item(e) for e in dashboard.upcoming_events],
            cash=DashboardCashOut.from_summary(dashboard.cash),
            receivables=DashboardReceivablesOut.from_receivables(dashboard.receivables),
            inventory=DashboardInventoryOut.from_alerts(dashboard.inventory),
            purchases=DashboardPurchasesOut.from_open(dashboard.purchases),
        )
