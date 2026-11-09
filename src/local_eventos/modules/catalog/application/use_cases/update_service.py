"""Caso de uso: modificar un servicio del catálogo (HU06).

Las cotizaciones ya hechas no cambian: guardan su propia copia del precio (AGENTS.md, regla 6).
"""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.catalog.application.errors import ServiceNotFoundError
from local_eventos.modules.catalog.application.ports.category_repository import (
    CategoryRepository,
)
from local_eventos.modules.catalog.application.ports.service_repository import (
    ServiceRepository,
)
from local_eventos.modules.catalog.application.use_cases.category_rules import (
    require_active_category,
)
from local_eventos.modules.catalog.domain.service import PriceUnit, Service


@dataclass(frozen=True)
class UpdateServiceCommand:
    service_id: UUID
    name: str
    category_id: UUID
    price_unit: PriceUnit
    reference_price_cents: int
    description: str | None = None


class UpdateService:
    def __init__(
        self, services: ServiceRepository, categories: CategoryRepository
    ) -> None:
        self._services = services
        self._categories = categories

    async def __call__(self, command: UpdateServiceCommand) -> Service:
        service = await self._services.get(command.service_id)
        if service is None:
            raise ServiceNotFoundError()
        if command.category_id != service.category_id:
            await require_active_category(self._categories, command.category_id)
        service.update(
            name=command.name,
            category_id=command.category_id,
            price_unit=command.price_unit,
            reference_price_cents=command.reference_price_cents,
            description=command.description,
        )
        await self._services.update(service)
        return service
