"""Ensamblaje de dependencias del módulo catalog.

Es el único lugar que conoce las clases concretas de `infrastructure`: el resto del módulo
trabaja con los puertos (`CategoryRepository`, `ServiceRepository`).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.catalog.application.ports.category_repository import (
    CategoryRepository,
)
from local_eventos.modules.catalog.application.ports.service_repository import (
    ServiceRepository,
)
from local_eventos.modules.catalog.infrastructure.category_repository import (
    SqlAlchemyCategoryRepository,
)
from local_eventos.modules.catalog.infrastructure.service_repository import (
    SqlAlchemyServiceRepository,
)


def category_repository(session: AsyncSession) -> CategoryRepository:
    return SqlAlchemyCategoryRepository(session)


def service_repository(session: AsyncSession) -> ServiceRepository:
    return SqlAlchemyServiceRepository(session)
