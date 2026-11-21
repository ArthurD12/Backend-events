"""Casos de uso: desactivar y reactivar un servicio sin eliminarlo (HU06, RN02)."""

from uuid import UUID

from local_eventos.modules.catalog.application.errors import ServiceNotFoundError
from local_eventos.modules.catalog.application.ports.service_repository import (
    ServiceRepository,
)
from local_eventos.modules.catalog.domain.service import Service


class DeactivateService:
    def __init__(self, services: ServiceRepository) -> None:
        self._services = services

    async def __call__(self, service_id: UUID) -> Service:
        service = await _get_or_fail(self._services, service_id)
        service.deactivate()
        await self._services.update(service)
        return service


class ActivateService:
    def __init__(self, services: ServiceRepository) -> None:
        self._services = services

    async def __call__(self, service_id: UUID) -> Service:
        service = await _get_or_fail(self._services, service_id)
        service.activate()
        await self._services.update(service)
        return service


async def _get_or_fail(services: ServiceRepository, service_id: UUID) -> Service:
    service = await services.get(service_id)
    if service is None:
        raise ServiceNotFoundError()
    return service
