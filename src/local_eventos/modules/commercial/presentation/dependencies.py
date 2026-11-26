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
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractRepository,
)
from local_eventos.modules.commercial.application.contracts.ports.receipt import (
    PaymentReceiptRenderer,
)
from local_eventos.modules.commercial.application.events.ports.event_log_repository import (
    EventLogRepository,
)
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventRepository,
)
from local_eventos.modules.commercial.application.events.ports.reservation_releaser import (
    ReservationReleaser,
)
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.application.quotes.ports.document import (
    CompanyProfile,
    QuoteDocumentRenderer,
)
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteRepository,
)
from local_eventos.modules.identity.public_api import CoordinatorLookup, UserNamesLookup
from local_eventos.modules.inventory.public_api import reservation_releaser
from local_eventos.modules.ledger.public_api import (
    PaymentEntriesLookup,
    PaymentFinder,
    PaymentRecorder,
    PaymentVoider,
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


async def get_contract_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ContractRepository:
    return composition.contract_repository(session)


async def get_payment_recorder(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentRecorder:
    return composition.payments(session)


async def get_payments_lookup(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentEntriesLookup:
    """Pagos del contrato con su anulación: con ellos se calcula el saldo (RN15)."""
    return composition.contract_payment_entries(session)


async def get_payment_finder(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentFinder:
    return composition.find_payment(session)


async def get_payment_voider(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentVoider:
    return composition.void_payment(session)


def get_receipt_renderer() -> PaymentReceiptRenderer:
    return composition.receipt_renderer()


async def get_user_names(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserNamesLookup:
    return composition.user_names(session)


Contracts = Annotated[ContractRepository, Depends(get_contract_repository)]
Payments = Annotated[PaymentRecorder, Depends(get_payment_recorder)]
PaymentHistory = Annotated[PaymentEntriesLookup, Depends(get_payments_lookup)]
PaymentFind = Annotated[PaymentFinder, Depends(get_payment_finder)]
PaymentVoid = Annotated[PaymentVoider, Depends(get_payment_voider)]
ReceiptRenderer = Annotated[PaymentReceiptRenderer, Depends(get_receipt_renderer)]
UserNames = Annotated[UserNamesLookup, Depends(get_user_names)]


async def get_event_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventRepository:
    return composition.event_repository(session)


async def get_reservation_releaser(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReservationReleaser:
    """Libera los materiales reservados por `inventory.public_api` (R-REC-3)."""
    return reservation_releaser(session)


Reservations = Annotated[ReservationReleaser, Depends(get_reservation_releaser)]


async def get_coordinator_lookup(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CoordinatorLookup:
    return composition.coordinators(session)


async def get_event_log_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventLogRepository:
    return composition.event_log_repository(session)


Events = Annotated[EventRepository, Depends(get_event_repository)]
Coordinators = Annotated[CoordinatorLookup, Depends(get_coordinator_lookup)]
EventLog = Annotated[EventLogRepository, Depends(get_event_log_repository)]
