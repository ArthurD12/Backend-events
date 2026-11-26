"""Ensamblaje del módulo purchasing: único lugar que conoce las clases de `infrastructure`."""

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial.public_api import (
    CompanyProfile,
    EventLookup,
    company_profile,
    event_lookup,
)
from local_eventos.modules.inventory.public_api import (
    EventRequirementLookup,
    LowStockLookup,
    ProductLookup,
    StockReceiver,
    event_requirement,
    low_stock_lookup,
    product_lookup,
    stock_receiver,
)
from local_eventos.modules.ledger.public_api import MovementRecorder, movement_recorder
from local_eventos.modules.purchasing.application.ports.clock import Clock
from local_eventos.modules.purchasing.application.ports.document import (
    PurchaseDocumentRenderer,
)
from local_eventos.modules.purchasing.application.ports.repositories import (
    PurchaseRepository,
    SupplierRepository,
)
from local_eventos.modules.purchasing.infrastructure.clock import LimaClock
from local_eventos.modules.purchasing.infrastructure.purchase_pdf import (
    ReportLabPurchaseRenderer,
)
from local_eventos.modules.purchasing.infrastructure.repositories import (
    SqlAlchemyPurchaseRepository,
    SqlAlchemySupplierRepository,
)


def supplier_repository(session: AsyncSession) -> SupplierRepository:
    return SqlAlchemySupplierRepository(session)


def purchase_repository(session: AsyncSession) -> PurchaseRepository:
    return SqlAlchemyPurchaseRepository(session)


def products(session: AsyncSession) -> ProductLookup:
    """Productos de inventory, por su `public_api` (AGENTS.md, regla 3)."""
    return product_lookup(session)


def low_stock(session: AsyncSession) -> LowStockLookup:
    return low_stock_lookup(session)


def receiver(session: AsyncSession) -> StockReceiver:
    """Entradas de almacén en la misma sesión (misma transacción) que la compra."""
    return stock_receiver(session)


def clock() -> Clock:
    return LimaClock()


def requirement(session: AsyncSession) -> EventRequirementLookup:
    """Requerimiento del evento (faltantes), por `inventory.public_api`."""
    return event_requirement(session)


def events(session: AsyncSession) -> EventLookup:
    """Código del evento para el PDF, por `commercial.public_api`."""
    return event_lookup(session)


def expenses(session: AsyncSession) -> MovementRecorder:
    """Egresos de caja en la misma sesión (misma transacción) que la compra."""
    return movement_recorder(session)


def document_renderer() -> PurchaseDocumentRenderer:
    return ReportLabPurchaseRenderer()


def company() -> CompanyProfile:
    return company_profile()
