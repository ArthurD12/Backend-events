"""Superficie pública del módulo commercial: única vía de uso por otros módulos.

Agrupa clientes, cotizaciones, contratos y eventos (ADR 0003). Otro módulo (por ejemplo,
ledger o assistant) importa solo desde aquí, nunca desde sus capas internas (AGENTS.md, regla 3).
"""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.commercial.application.clients.use_cases.get_client_summary import (
    ClientSummary,
)


class ClientLookup(Protocol):
    """Busca un cliente por su ID. Devuelve `None` si no existe."""

    async def __call__(self, client_id: UUID) -> ClientSummary | None: ...


__all__ = ["ClientLookup", "ClientSummary"]
