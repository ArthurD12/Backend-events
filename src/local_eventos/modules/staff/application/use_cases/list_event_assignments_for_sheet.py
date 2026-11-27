"""Caso de uso: asignaciones de un evento para la ficha de HU14 (HU17, T-10).

Es la consulta de solo lectura que `staff.public_api` expondrá a `reporting`
para el bloque «Personal asignado» (CA-17.21, plan §1.4). Devuelve las
asignaciones `ACTIVE` del evento como `EventAssignment`: nombre del trabajador,
función, descripción e instantes UTC, **nunca el pago**, documento, teléfono ni
tarifa.

No valida la existencia del evento ni lanza 404: el `event_id` ya lo validó el
llamador (el adaptador de HU14 lo usará con un evento existente). Si el evento
no tiene asignaciones, devuelve una lista vacía.

Python puro: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from uuid import UUID

from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentRepository,
    EventAssignment,
)

__all__ = ["ListEventAssignmentsForSheet"]


class ListEventAssignmentsForSheet:
    """Devuelve las asignaciones activas del evento sin datos económicos."""

    def __init__(self, assignments: AssignmentRepository) -> None:
        self._assignments = assignments

    async def execute(self, event_id: UUID) -> list[EventAssignment]:
        """Mapea las asignaciones del evento a la superficie pública sin pago.

        Devuelve lista vacía si no hay asignaciones (no lanza 404).
        """
        views = await self._assignments.list_by_event(event_id)
        return [
            EventAssignment(
                worker_id=view.worker_id,
                worker_name=view.worker_name,
                function=view.function,
                function_description=view.function_description,
                starts_at=view.start_at,
                ends_at=view.end_at,
            )
            for view in views
        ]
