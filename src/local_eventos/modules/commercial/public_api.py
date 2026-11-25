"""Superficie pública del módulo commercial: única vía de uso por otros módulos.

Agrupa clientes, cotizaciones, contratos y eventos (ADR 0003). Otro módulo (por ejemplo,
ledger o assistant) importa solo desde aquí, nunca desde sus capas internas (AGENTS.md, regla 3).
"""

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial import composition
from local_eventos.modules.commercial.application.clients.use_cases.get_client_summary import (
    ClientSummary,
)
from local_eventos.modules.commercial.application.events.use_cases.event_finance import (
    EventFinance,
    GetEventFinance,
)
from local_eventos.modules.commercial.application.events.use_cases.event_lookup import (
    EventInfo,
    LookupEvent,
)
from local_eventos.modules.commercial.application.events.use_cases.event_reports import (
    EventRefs,
    EventReportFilters,
    EventReportItem,
    GetReceivables,
    ListEventReport,
    ListUpcomingEvents,
    LookupEventRefs,
    Receivables,
)
from local_eventos.modules.commercial.application.events.use_cases.event_sheet import (
    AccountPaymentInfo,
    ActivityInfo,
    EventAccount,
    EventDetail,
    EventFollowUp,
    EventServiceInfo,
    GetEventAccount,
    GetEventDetail,
    GetEventFollowUp,
    NoteInfo,
)
from local_eventos.modules.commercial.application.quotes.ports.document import CompanyProfile
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteSummary,
)
from local_eventos.modules.commercial.application.quotes.use_cases.quote_stats import (
    GetQuoteStats,
    QuoteStats,
)
from local_eventos.modules.commercial.domain.contracts.contract import ContractStatus
from local_eventos.modules.commercial.domain.events.activity import ActivityStatus
from local_eventos.modules.commercial.domain.events.event import EventStatus
from local_eventos.modules.commercial.domain.quotes.quote import EventType, LineKind, LineUnit


class ClientLookup(Protocol):
    """Busca un cliente por su ID. Devuelve `None` si no existe."""

    async def __call__(self, client_id: UUID) -> ClientSummary | None: ...


class QuoteStatsLookup(Protocol):
    """Números de cotizaciones del mes indicado (por defecto, el actual en Lima)."""

    async def __call__(self, year: int | None = None, month: int | None = None) -> QuoteStats: ...


class EventFinanceLookup(Protocol):
    """Total contratado, cobrado y saldo del evento por su contrato. `None` si no existe."""

    async def __call__(self, event_id: UUID) -> EventFinance | None: ...


def event_finance(session: AsyncSession) -> EventFinanceLookup:
    """Consulta de solo lectura para el resultado económico del evento (HU22)."""
    return GetEventFinance(
        composition.event_repository(session),
        composition.contract_repository(session),
        composition.client_repository(session),
        composition.contract_payment_entries(session),
    )


class EventLookup(Protocol):
    """Busca un evento por su ID (código, estado, fecha y horario). `None` si no existe."""

    async def __call__(self, event_id: UUID) -> EventInfo | None: ...


def event_lookup(session: AsyncSession) -> EventLookup:
    """Consulta de solo lectura de eventos, dentro de la transacción de la petición."""
    return LookupEvent(composition.event_repository(session))


class EventDetailLookup(Protocol):
    """Evento con su cliente y servicios contratados, sin precios (HU14). `None` si no existe."""

    async def __call__(self, event_id: UUID) -> EventDetail | None: ...


class EventFollowUpLookup(Protocol):
    """Actividades del evento y sus últimas observaciones (HU13 → HU14)."""

    async def __call__(self, event_id: UUID) -> EventFollowUp: ...


class EventAccountLookup(Protocol):
    """Cuenta del contrato del evento: total, pagado, saldo y pagos (HU19 → HU14)."""

    async def __call__(self, event_id: UUID) -> EventAccount | None: ...


def event_detail(session: AsyncSession) -> EventDetailLookup:
    """Consulta de solo lectura para la ficha del evento (HU14)."""
    return GetEventDetail(
        composition.event_repository(session), composition.client_repository(session)
    )


def event_follow_up(session: AsyncSession) -> EventFollowUpLookup:
    return GetEventFollowUp(composition.event_log_repository(session))


def event_account(session: AsyncSession) -> EventAccountLookup:
    return GetEventAccount(
        composition.event_repository(session),
        composition.contract_repository(session),
        composition.contract_payment_entries(session),
        composition.clock(),
    )


def quote_stats(session: AsyncSession) -> QuoteStatsLookup:
    """Consulta de solo lectura para el panel (HU31), dentro de la transacción de la petición."""
    return GetQuoteStats(composition.quote_repository(session), composition.clock())


class EventReportLookup(Protocol):
    """Eventos del filtro con total contratado, pagado y saldo (reporte de eventos, CA-32.1)."""

    async def __call__(self, filters: EventReportFilters) -> list[EventReportItem]: ...


class UpcomingEventsLookup(Protocol):
    """Eventos de hoy a `days` días, sin cancelados ni finalizados, con su saldo (CA-31.7)."""

    async def __call__(self, days: int = 14) -> list[EventReportItem]: ...


class ReceivablesLookup(Protocol):
    """Total por cobrar de contratos firmados y cuántos tienen el saldo vencido (CA-31.9)."""

    async def __call__(self) -> Receivables: ...


class EventRefsLookup(Protocol):
    """Códigos de eventos por su ID o por el de su contrato, para los reportes."""

    async def __call__(self, event_ids: list[UUID], contract_ids: list[UUID]) -> EventRefs: ...


def events_report(session: AsyncSession) -> EventReportLookup:
    """Consulta de solo lectura para el reporte de eventos (HU32–HU34)."""
    return ListEventReport(
        composition.event_repository(session),
        composition.contract_repository(session),
        composition.paid_totals(session),
        composition.clock(),
    )


def upcoming_events(session: AsyncSession) -> UpcomingEventsLookup:
    """Consulta de solo lectura para el panel (HU31)."""
    report = ListEventReport(
        composition.event_repository(session),
        composition.contract_repository(session),
        composition.paid_totals(session),
        composition.clock(),
    )
    return ListUpcomingEvents(report, composition.clock())


def receivables(session: AsyncSession) -> ReceivablesLookup:
    """Consulta de solo lectura para el panel (HU31)."""
    return GetReceivables(
        composition.contract_repository(session),
        composition.paid_totals(session),
        composition.clock(),
    )


def event_refs(session: AsyncSession) -> EventRefsLookup:
    """Consulta de solo lectura: nombra eventos y contratos en los reportes."""
    return LookupEventRefs(
        composition.event_repository(session), composition.contract_repository(session)
    )


def company_profile() -> CompanyProfile:
    """Datos de Darze del `.env` (COMPANY_*) para el encabezado de los documentos."""
    return composition.company_profile()


__all__ = [
    "AccountPaymentInfo",
    "CompanyProfile",
    "ActivityInfo",
    "ActivityStatus",
    "ClientLookup",
    "ClientSummary",
    "ContractStatus",
    "EventAccount",
    "EventAccountLookup",
    "EventDetail",
    "EventDetailLookup",
    "EventFinance",
    "EventFinanceLookup",
    "EventFollowUp",
    "EventFollowUpLookup",
    "EventInfo",
    "EventLookup",
    "EventRefs",
    "EventRefsLookup",
    "EventReportFilters",
    "EventReportItem",
    "EventReportLookup",
    "EventServiceInfo",
    "EventStatus",
    "EventType",
    "LineKind",
    "LineUnit",
    "NoteInfo",
    "QuoteStats",
    "QuoteStatsLookup",
    "QuoteSummary",
    "Receivables",
    "ReceivablesLookup",
    "UpcomingEventsLookup",
    "company_profile",
    "event_account",
    "event_detail",
    "event_finance",
    "event_follow_up",
    "event_lookup",
    "event_refs",
    "events_report",
    "quote_stats",
    "receivables",
    "upcoming_events",
]
