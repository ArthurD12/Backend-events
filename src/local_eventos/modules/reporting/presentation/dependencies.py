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
    event_account,
    event_detail,
    event_finance,
    event_follow_up,
    quote_stats,
)
from local_eventos.modules.identity.public_api import UserNamesLookup, user_names
from local_eventos.modules.inventory.public_api import EventMaterialsLookup, event_materials
from local_eventos.modules.ledger.public_api import (
    CashTotalsLookup,
    EventCashLookup,
    cash_totals,
    event_cash,
)
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
