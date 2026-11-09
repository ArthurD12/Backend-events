"""Superficie pública del módulo catalog: única vía de uso por otros módulos.

Otro módulo (por ejemplo, quotes) importa solo desde aquí, nunca desde domain,
application o infrastructure de catalog (AGENTS.md, regla 3).
"""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.catalog.application.use_cases.get_service_summary import (
    ServiceSummary,
)


class ServiceLookup(Protocol):
    """Busca un servicio por su ID. Devuelve `None` si no existe."""

    async def __call__(self, service_id: UUID) -> ServiceSummary | None: ...


__all__ = ["ServiceLookup", "ServiceSummary"]
