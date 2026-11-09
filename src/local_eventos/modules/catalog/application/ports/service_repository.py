"""Puerto: cómo la aplicación guarda y lee servicios. La base de datos lo implementa."""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.catalog.domain.service import Service


class ServiceRepository(Protocol):
    async def get(self, service_id: UUID) -> Service | None: ...

    async def add(self, service: Service) -> None: ...

    async def update(self, service: Service) -> None: ...

    async def search(
        self,
        text: str,
        *,
        category_id: UUID | None,
        active: bool | None,
        limit: int,
    ) -> list[Service]:
        """Filtra por nombre (contiene, sin distinguir mayúsculas), categoría y estado.

        Un filtro en `None` no filtra. Texto vacío devuelve todos. Ordenados por nombre.
        """
        ...
