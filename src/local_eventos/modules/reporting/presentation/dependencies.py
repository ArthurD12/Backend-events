"""Dependencias de FastAPI del módulo reporting. En las pruebas se reemplazan por fakes."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial.public_api import QuoteStatsLookup, quote_stats
from local_eventos.shared.presentation.database import get_session


async def get_quote_stats(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> QuoteStatsLookup:
    return quote_stats(session)


QuoteStatsDep = Annotated[QuoteStatsLookup, Depends(get_quote_stats)]
