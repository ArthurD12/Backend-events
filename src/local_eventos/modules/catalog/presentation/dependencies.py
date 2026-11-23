"""Dependencias de FastAPI del módulo catalog: qué recibe cada endpoint.

Los dos repositorios usan la misma sesión (FastAPI la reutiliza dentro de una petición),
así que todo lo que hace un endpoint se confirma o se deshace junto.
En las pruebas se reemplazan por repositorios en memoria.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.catalog import composition
from local_eventos.modules.catalog.application.ports.category_repository import (
    CategoryRepository,
)
from local_eventos.modules.catalog.application.ports.service_repository import (
    ServiceRepository,
)
from local_eventos.shared.presentation.database import get_session


async def get_category_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CategoryRepository:
    return composition.category_repository(session)


async def get_service_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ServiceRepository:
    return composition.service_repository(session)


Categories = Annotated[CategoryRepository, Depends(get_category_repository)]
Services = Annotated[ServiceRepository, Depends(get_service_repository)]
