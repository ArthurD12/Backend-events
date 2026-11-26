"""Caso de uso: consultar el detalle de una asignación (HU17, T-10, plan §3.4).

Devuelve la vista completa de una asignación por id, **incluidas las anuladas**
(CA-17.16), para la pantalla de detalle. La vista no filtra por estado; el
listado vigente es responsabilidad de `ListEventAssignments`.

Python puro: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from uuid import UUID

from local_eventos.modules.staff.application.errors import AssignmentNotFoundError
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentRepository,
    AssignmentView,
)

__all__ = ["GetAssignment"]


class GetAssignment:
    """Recupera la vista de una asignación por su identificador."""

    def __init__(self, assignments: AssignmentRepository) -> None:
        self._assignments = assignments

    async def execute(self, assignment_id: UUID) -> AssignmentView:
        """Devuelve la asignación, activa o anulada.

        Lanza `AssignmentNotFoundError` (`staff.assignment_not_found`, 404) si el
        id no existe.
        """
        view = await self._assignments.get_view(assignment_id)
        if view is None:
            raise AssignmentNotFoundError()
        return view
