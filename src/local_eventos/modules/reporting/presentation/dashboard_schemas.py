"""Forma de la respuesta del panel del administrador (HU31)."""

from datetime import date
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.commercial.public_api import QuoteStats, QuoteSummary
from local_eventos.modules.reporting.application.use_cases.get_dashboard import Dashboard


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
        description="Aceptadas con evento en los próximos 30 días"
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


class DashboardOut(BaseModel):
    month: str = Field(description="AAAA-MM")
    currency: str = "PEN"
    quotes: DashboardQuotesOut

    @classmethod
    def from_dashboard(cls, dashboard: Dashboard) -> Self:
        return cls(
            month=f"{dashboard.year:04d}-{dashboard.month:02d}",
            quotes=DashboardQuotesOut.from_stats(dashboard.quotes),
        )
