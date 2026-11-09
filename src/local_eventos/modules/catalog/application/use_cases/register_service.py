"""Caso de uso: registrar un servicio en el catálogo (HU06)."""

from dataclasses import dataclass
from uuid import UUID

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
class RegisterServiceCommand:
    name: str
    category_id: UUID
    price_unit: PriceUnit
    reference_price_cents: int
    description: str | None = None


class RegisterService:
    def __init__(
        self, services: ServiceRepository, categories: CategoryRepository
    ) -> None:
        self._services = services
        self._categories = categories

    async def __call__(self, command: RegisterServiceCommand) -> Service:
        service = Service.register(
            name=command.name,
            category_id=command.category_id,
            price_unit=command.price_unit,
            reference_price_cents=command.reference_price_cents,
            description=command.description,
        )
        await require_active_category(self._categories, command.category_id)
        await self._services.add(service)
        return service
