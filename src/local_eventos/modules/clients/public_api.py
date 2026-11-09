"""Superficie pública del módulo clients: única vía de uso por otros módulos.

Otro módulo (por ejemplo, quotes) importa solo desde aquí, nunca desde domain,
application o infrastructure de clients (AGENTS.md, regla 3).
"""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.clients.application.use_cases.get_client_summary import (
    ClientSummary,
)


class ClientLookup(Protocol):
    """Busca un cliente por su ID. Devuelve `None` si no existe."""

    async def __call__(self, client_id: UUID) -> ClientSummary | None: ...


__all__ = ["ClientLookup", "ClientSummary"]
