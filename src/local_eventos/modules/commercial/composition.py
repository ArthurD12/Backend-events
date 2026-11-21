"""Ensamblaje de dependencias del módulo commercial.

Es el único lugar que conoce las clases concretas de `infrastructure`: el resto del módulo
trabaja con los puertos (por ejemplo, `ClientRepository`).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial.application.clients.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.commercial.infrastructure.client_repository import (
    SqlAlchemyClientRepository,
)


def client_repository(session: AsyncSession) -> ClientRepository:
    return SqlAlchemyClientRepository(session)
