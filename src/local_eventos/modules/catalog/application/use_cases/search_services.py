"""Caso de uso: buscar en el catálogo por nombre, categoría o estado (HU06).

Por defecto devuelve solo servicios activos: es lo que necesita una cotización.
"""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.catalog.application.ports.service_repository import (
    ServiceRepository,
)
from local_eventos.modules.catalog.domain.service import Service

MAX_RESULTS = 50


@dataclass(frozen=True)
class SearchServicesQuery:
    text: str = ""
    category_id: UUID | None = None
    active: bool | None = True


class SearchServices:
    def __init__(self, services: ServiceRepository) -> None:
        self._services = services

    async def __call__(self, query: SearchServicesQuery) -> list[Service]:
        return await self._services.search(
            " ".join(query.text.split()),
            category_id=query.category_id,
            active=query.active,
            limit=MAX_RESULTS,
        )
