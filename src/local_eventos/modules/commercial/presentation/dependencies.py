"""Dependencias de FastAPI del módulo commercial: qué recibe cada endpoint.

En las pruebas se reemplaza `get_client_repository` por un repositorio en memoria.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.catalog.public_api import ServiceLookup
from local_eventos.modules.commercial import composition
from local_eventos.modules.commercial.application.clients.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.application.quotes.ports.document import (
    CompanyProfile,
    QuoteDocumentRenderer,
)
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteRepository,
)
from local_eventos.shared.presentation.database import get_session


async def get_client_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ClientRepository:
    return composition.client_repository(session)


Clients = Annotated[ClientRepository, Depends(get_client_repository)]


async def get_quote_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> QuoteRepository:
    return composition.quote_repository(session)


async def get_service_lookup(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ServiceLookup:
    return composition.service_lookup(session)


def get_clock() -> Clock:
    return composition.clock()


Quotes = Annotated[QuoteRepository, Depends(get_quote_repository)]
Services = Annotated[ServiceLookup, Depends(get_service_lookup)]
Today = Annotated[Clock, Depends(get_clock)]


def get_quote_renderer() -> QuoteDocumentRenderer:
    return composition.quote_renderer()


def get_company_profile() -> CompanyProfile:
    return composition.company_profile()


Renderer = Annotated[QuoteDocumentRenderer, Depends(get_quote_renderer)]
Company = Annotated[CompanyProfile, Depends(get_company_profile)]
