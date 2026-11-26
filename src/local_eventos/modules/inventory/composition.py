"""Ensamblaje del módulo inventory: único lugar que conoce las clases de `infrastructure`."""

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.catalog.public_api import ServiceLookup, service_lookup
from local_eventos.modules.commercial.public_api import EventLookup
from local_eventos.modules.commercial.public_api import event_lookup as commercial_event_lookup
from local_eventos.modules.inventory.application.ports.clock import Clock
from local_eventos.modules.inventory.application.ports.product_repository import (
    ProductRepository,
)
from local_eventos.modules.inventory.application.ports.recipe_repository import RecipeRepository
from local_eventos.modules.inventory.application.ports.stock_repository import (
    MovementRepository,
    StockRepository,
)
from local_eventos.modules.inventory.application.use_cases.movements import RecordMovement
from local_eventos.modules.inventory.infrastructure.clock import LimaClock
from local_eventos.modules.inventory.infrastructure.product_repository import (
    SqlAlchemyProductRepository,
)
from local_eventos.modules.inventory.infrastructure.recipe_repository import (
    SqlAlchemyRecipeRepository,
)
from local_eventos.modules.inventory.infrastructure.stock_repository import (
    SqlAlchemyMovementRepository,
    SqlAlchemyStockRepository,
)


def product_repository(session: AsyncSession) -> ProductRepository:
    return SqlAlchemyProductRepository(session)


def stock_repository(session: AsyncSession) -> StockRepository:
    return SqlAlchemyStockRepository(session)


def movement_repository(session: AsyncSession) -> MovementRepository:
    return SqlAlchemyMovementRepository(session)


def recipe_repository(session: AsyncSession) -> RecipeRepository:
    return SqlAlchemyRecipeRepository(session)


def services(session: AsyncSession) -> ServiceLookup:
    """Servicios del catálogo, por su `public_api` (AGENTS.md, regla 3)."""
    return service_lookup(session)


def events(session: AsyncSession) -> EventLookup:
    """Eventos de commercial, por su `public_api` (AGENTS.md, regla 3)."""
    return commercial_event_lookup(session)


def clock() -> Clock:
    return LimaClock()


def record_movement(session: AsyncSession) -> RecordMovement:
    return RecordMovement(
        product_repository(session),
        stock_repository(session),
        movement_repository(session),
        events(session),
        clock(),
    )
