"""Superficie pública del módulo catalog: única vía de uso por otros módulos.

Otro módulo (por ejemplo, commercial) importa solo desde aquí, nunca desde domain,
application o infrastructure de catalog (AGENTS.md, regla 3).
"""

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.catalog import composition
from local_eventos.modules.catalog.application.use_cases.get_service_summary import (
    GetServiceSummary,
    ServiceSummary,
)


class ServiceLookup(Protocol):
    """Busca un servicio por su ID. Devuelve `None` si no existe."""

    async def __call__(self, service_id: UUID) -> ServiceSummary | None: ...


def service_lookup(session: AsyncSession) -> ServiceLookup:
    """Consulta de servicios para otros módulos, dentro de la misma transacción de la petición."""
    return GetServiceSummary(composition.service_repository(session))


__all__ = ["ServiceLookup", "ServiceSummary", "service_lookup"]
