"""Consulta para otros módulos: datos de un servicio del catálogo (HU06 → HU07).

Cotizaciones usa esta copia para congelar el nombre y el precio en la cotización
(AGENTS.md, regla 6). Nunca recibe la entidad `Service`, así que no puede modificarla.
"""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.catalog.application.ports.service_repository import (
    ServiceRepository,
)
from local_eventos.modules.catalog.domain.service import CURRENCY


@dataclass(frozen=True)
class ServiceSummary:
    id: UUID
    name: str
    category_id: UUID
    price_unit: str
    reference_price_cents: int
    currency: str
    active: bool


class GetServiceSummary:
    def __init__(self, services: ServiceRepository) -> None:
        self._services = services

    async def __call__(self, service_id: UUID) -> ServiceSummary | None:
        """Devuelve `None` si no existe: cada módulo decide qué error mostrar."""
        service = await self._services.get(service_id)
        if service is None:
            return None
        return ServiceSummary(
            id=service.id,
            name=service.name,
            category_id=service.category_id,
            price_unit=service.price_unit.value,
            reference_price_cents=service.reference_price_cents,
            currency=CURRENCY,
            active=service.active,
        )
