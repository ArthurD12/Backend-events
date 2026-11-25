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
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractRepository,
)
from local_eventos.modules.commercial.application.contracts.ports.receipt import (
    PaymentReceiptRenderer,
)
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventRepository,
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
from local_eventos.modules.commercial.infrastructure.contract_repository import (
    SqlAlchemyContractRepository,
)
from local_eventos.modules.commercial.infrastructure.event_repository import (
    SqlAlchemyEventRepository,
)
from local_eventos.modules.commercial.infrastructure.quote_pdf import ReportLabQuoteRenderer
from local_eventos.modules.commercial.infrastructure.quote_repository import (
    SqlAlchemyQuoteRepository,
)
from local_eventos.modules.commercial.infrastructure.receipt_pdf import ReportLabReceiptRenderer
from local_eventos.modules.identity.public_api import CoordinatorLookup, UserNamesLookup
from local_eventos.modules.identity.public_api import coordinator_lookup as identity_coordinators
from local_eventos.modules.identity.public_api import user_names as identity_user_names
from local_eventos.modules.ledger.public_api import (
    PaymentEntriesLookup,
    PaymentFinder,
    PaymentRecorder,
    PaymentsLookup,
    PaymentVoider,
    payment_entries,
    payment_finder,
    payment_recorder,
    payment_voider,
    payments_lookup,
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


def contract_repository(session: AsyncSession) -> ContractRepository:
    return SqlAlchemyContractRepository(session)


def payments(session: AsyncSession) -> PaymentRecorder:
    """Registro de pagos del módulo ledger, por su `public_api` (AGENTS.md, regla 3)."""
    return payment_recorder(session)


def contract_payments(session: AsyncSession) -> PaymentsLookup:
    return payments_lookup(session)


def contract_payment_entries(session: AsyncSession) -> PaymentEntriesLookup:
    """Pagos del contrato con su anulación, para calcular el saldo (RN15)."""
    return payment_entries(session)


def find_payment(session: AsyncSession) -> PaymentFinder:
    return payment_finder(session)


def void_payment(session: AsyncSession) -> PaymentVoider:
    return payment_voider(session)


def receipt_renderer() -> PaymentReceiptRenderer:
    return ReportLabReceiptRenderer()


def user_names(session: AsyncSession) -> UserNamesLookup:
    """Quién registró cada pago, por la `public_api` de identity."""
    return identity_user_names(session)


def event_repository(session: AsyncSession) -> EventRepository:
    return SqlAlchemyEventRepository(session)


def coordinators(session: AsyncSession) -> CoordinatorLookup:
    """Quiénes pueden coordinar un evento, por la `public_api` de identity (R-EVT-2)."""
    return identity_coordinators(session)
