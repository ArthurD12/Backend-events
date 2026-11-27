"""Lectura de la función de una asignación para HU16 (T-08).

Implementa el puerto `AssignmentConflictLookup` con **una sola** consulta
`WHERE id IN (...)` sobre `staff_assignments`, proyectando únicamente `id`,
`worker_function` y `function_description`. Los ids llegan siempre desde
`AssignmentRepository.list_active_overlaps` (HU17): aquí no se añaden predicados
temporales ni de estado y no se reimplementa el criterio de solape.

No lee ni expone pago, tarifa, documento ni teléfono, y no usa `AssignmentView`.
Es una lectura de solo lectura: no escribe ni confirma transacción (plan §3.1).
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.staff.application.ports.assignment_conflict_lookup import (
    AssignmentFunction,
)
from local_eventos.modules.staff.domain.enums import WorkerFunction
from local_eventos.modules.staff.infrastructure.orm_models import StaffAssignmentRow


class SqlAlchemyAssignmentConflictLookup:
    """Adaptador async del puerto, sobre la sesión de la petición."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def by_ids(self, assignment_ids: Sequence[UUID]) -> dict[UUID, AssignmentFunction | None]:
        ids = list(dict.fromkeys(assignment_ids))
        if not ids:
            return {}
        rows = (
            await self._session.execute(
                select(
                    StaffAssignmentRow.id,
                    StaffAssignmentRow.worker_function,
                    StaffAssignmentRow.function_description,
                ).where(StaffAssignmentRow.id.in_(ids))
            )
        ).all()
        found: dict[UUID, AssignmentFunction] = {
            row.id: AssignmentFunction(
                worker_function=WorkerFunction(row.worker_function),
                function_description=row.function_description,
            )
            for row in rows
        }
        return {assignment_id: found.get(assignment_id) for assignment_id in ids}
