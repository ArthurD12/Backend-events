"""Caso de uso: listar las asignaciones vigentes de un evento (HU17, T-10, plan §3.4).

Valida que el evento exista por `commercial.public_api.event_lookup` (404 si no
existe) y devuelve las asignaciones `ACTIVE` del evento ordenadas por `start_at`,
con nombre del trabajador, función/descripción, instantes UTC, pago, código y
estado del evento (CA-17.12). Las anuladas quedan fuera de esta lista
(CA-17.16); para verlas se usa `GetAssignment`.

Python puro: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from uuid import UUID

from local_eventos.modules.commercial.public_api import EventLookup
from local_eventos.modules.staff.application.errors import EventNotFoundError
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentRepository,
    AssignmentView,
)

__all__ = ["ListEventAssignments"]


class ListEventAssignments:
    """Lista las asignaciones activas de un evento, ordenadas por inicio."""

    def __init__(
        self,
        assignments: AssignmentRepository,
        event_lookup: EventLookup,
    ) -> None:
        self._assignments = assignments
        self._event_lookup = event_lookup

    async def execute(self, event_id: UUID) -> list[AssignmentView]:
        """Devuelve las asignaciones `ACTIVE` del evento con pago.

        Lanza `EventNotFoundError` (`staff.event_not_found`, 404) si el evento no
        existe. La lista no incluye asignaciones anuladas.
        """
        event = await self._event_lookup(event_id)
        if event is None:
            raise EventNotFoundError()
        return await self._assignments.list_by_event(event_id)
