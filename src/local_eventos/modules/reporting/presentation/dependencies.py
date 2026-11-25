"""Dependencias de FastAPI del módulo reporting. En las pruebas se reemplazan por fakes."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial.public_api import (
    EventAccountLookup,
    EventDetailLookup,
    EventFinanceLookup,
    EventFollowUpLookup,
    QuoteStatsLookup,
    ReceivablesLookup,
    UpcomingEventsLookup,
    event_account,
    event_detail,
    event_finance,
    event_follow_up,
    quote_stats,
    receivables,
    upcoming_events,
)
from local_eventos.modules.identity.public_api import UserNamesLookup, user_names
from local_eventos.modules.inventory.public_api import (
    EventMaterialsLookup,
    StockReportLookup,
    event_materials,
    stock_report,
)
from local_eventos.modules.ledger.public_api import (
    CashTotalsLookup,
    EventCashLookup,
    cash_totals,
    event_cash,
)
from local_eventos.modules.purchasing.public_api import OpenPurchasesLookup, open_purchases
from local_eventos.modules.reporting import composition
from local_eventos.modules.reporting.application.ports.event_staff import EventStaffLookup
from local_eventos.shared.presentation.database import get_session


async def get_quote_stats(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> QuoteStatsLookup:
    return quote_stats(session)


QuoteStatsDep = Annotated[QuoteStatsLookup, Depends(get_quote_stats)]


async def get_cash_totals(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CashTotalsLookup:
    return cash_totals(session)


async def get_event_finance(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventFinanceLookup:
    return event_finance(session)


async def get_event_cash(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventCashLookup:
    return event_cash(session)


CashTotalsDep = Annotated[CashTotalsLookup, Depends(get_cash_totals)]
EventFinanceDep = Annotated[EventFinanceLookup, Depends(get_event_finance)]
EventCashDep = Annotated[EventCashLookup, Depends(get_event_cash)]


async def get_event_detail(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventDetailLookup:
    return event_detail(session)


async def get_event_follow_up(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventFollowUpLookup:
    return event_follow_up(session)


async def get_event_materials(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventMaterialsLookup:
    return event_materials(session)


async def get_event_account(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventAccountLookup:
    return event_account(session)


async def get_event_staff() -> EventStaffLookup:
    return composition.event_staff()


async def get_user_names(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserNamesLookup:
    return user_names(session)


EventDetailDep = Annotated[EventDetailLookup, Depends(get_event_detail)]
EventFollowUpDep = Annotated[EventFollowUpLookup, Depends(get_event_follow_up)]
EventMaterialsDep = Annotated[EventMaterialsLookup, Depends(get_event_materials)]
EventAccountDep = Annotated[EventAccountLookup, Depends(get_event_account)]
EventStaffDep = Annotated[EventStaffLookup, Depends(get_event_staff)]
UserNamesDep = Annotated[UserNamesLookup, Depends(get_user_names)]


async def get_upcoming_events(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UpcomingEventsLookup:
    return upcoming_events(session)


async def get_receivables(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReceivablesLookup:
    return receivables(session)


async def get_stock_report(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StockReportLookup:
    return stock_report(session)


async def get_open_purchases(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OpenPurchasesLookup:
    return open_purchases(session)


UpcomingEventsDep = Annotated[UpcomingEventsLookup, Depends(get_upcoming_events)]
ReceivablesDep = Annotated[ReceivablesLookup, Depends(get_receivables)]
StockReportDep = Annotated[StockReportLookup, Depends(get_stock_report)]
OpenPurchasesDep = Annotated[OpenPurchasesLookup, Depends(get_open_purchases)]
