"""Ensamblaje de dependencias del módulo commercial.

Es el único lugar que conoce las clases concretas de `infrastructure`: el resto del módulo
trabaja con los puertos (por ejemplo, `ClientRepository`).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.catalog.public_api import ServiceLookup
from local_eventos.modules.catalog.public_api import service_lookup as catalog_service_lookup
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
from local_eventos.modules.commercial.infrastructure.client_repository import (
    SqlAlchemyClientRepository,
)
from local_eventos.modules.commercial.infrastructure.clock import LimaClock
from local_eventos.modules.commercial.infrastructure.company_settings import CompanySettings
from local_eventos.modules.commercial.infrastructure.quote_pdf import ReportLabQuoteRenderer
from local_eventos.modules.commercial.infrastructure.quote_repository import (
    SqlAlchemyQuoteRepository,
)


def client_repository(session: AsyncSession) -> ClientRepository:
    return SqlAlchemyClientRepository(session)


def quote_repository(session: AsyncSession) -> QuoteRepository:
    return SqlAlchemyQuoteRepository(session)


def service_lookup(session: AsyncSession) -> ServiceLookup:
    """Servicios del catálogo, consultados por su `public_api` (AGENTS.md, regla 3)."""
    return catalog_service_lookup(session)


def clock() -> Clock:
    return LimaClock()


def quote_renderer() -> QuoteDocumentRenderer:
    return ReportLabQuoteRenderer()


def company_profile() -> CompanyProfile:
    """Datos de Darze del `.env` (COMPANY_*). Se leen al pedir el documento."""
    return CompanySettings().profile()
