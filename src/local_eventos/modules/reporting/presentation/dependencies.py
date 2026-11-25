"""Dependencias de FastAPI del módulo reporting. En las pruebas se reemplazan por fakes."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial.public_api import (
    EventFinanceLookup,
    QuoteStatsLookup,
    event_finance,
    quote_stats,
)
from local_eventos.modules.ledger.public_api import (
    CashTotalsLookup,
    EventCashLookup,
    cash_totals,
    event_cash,
)
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
