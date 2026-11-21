"""Dependencias de FastAPI del módulo commercial: qué recibe cada endpoint.

En las pruebas se reemplaza `get_client_repository` por un repositorio en memoria.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial import composition
from local_eventos.modules.commercial.application.clients.ports.client_repository import (
    ClientRepository,
)
from local_eventos.shared.presentation.database import get_session


async def get_client_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ClientRepository:
    return composition.client_repository(session)


Clients = Annotated[ClientRepository, Depends(get_client_repository)]
