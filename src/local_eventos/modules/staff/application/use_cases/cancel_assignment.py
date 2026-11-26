"""Caso de uso: anular lógicamente una asignación (HU17, T-09, plan §3.3).

Flujo: el motivo es obligatorio desde el inicio y se valida antes de cualquier
lectura (R-ASG-8, RN03). Se lee la asignación sin bloqueo para conocer el
trabajador, se bloquea primero la fila del trabajador y después la asignación
(orden fijo para evitar deadlocks, plan §5.5) y se relee. El evento debe existir y
seguir admitiendo cambios: `FINISHED` y `CANCELLED` son de solo lectura
(CA-17.24, R-ASG-18). La anulación es idempotente: si la asignación ya está
`CANCELLED` se devuelve sin escribir una segunda auditoría. En caso contrario se
anula, se libera la ocupación y se escribe `CANCELLED` con motivo, actor y
fecha-hora en la misma transacción (CA-17.16, R-ASG-8/9). No hay borrado físico.

Python puro: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from uuid import UUID

from local_eventos.modules.commercial.public_api import EventLookup, EventStatus
from local_eventos.modules.staff.application.errors import (
    AssignmentNotFoundError,
    EventNotAssignableError,
    EventNotFoundError,
)
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentRepository,
)
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import AssignmentAudit
from local_eventos.modules.staff.domain.enums import AssignmentStatus
from local_eventos.modules.staff.domain.errors import AssignmentReasonRequiredError

_READ_ONLY_EVENT_STATUSES = frozenset({EventStatus.FINISHED, EventStatus.CANCELLED})


class CancelAssignment:
    """Anula lógicamente una asignación, audita el motivo y libera la ocupación."""

    def __init__(
        self,
        assignments: AssignmentRepository,
        event_lookup: EventLookup,
        clock: Clock,
    ) -> None:
        self._assignments = assignments
        self._event_lookup = event_lookup
        self._clock = clock

    async def execute(
        self,
        *,
        assignment_id: UUID,
        reason: str,
        actor_id: UUID,
    ) -> Assignment:
        """Anula la asignación y devuelve el agregado persistido.

        Lanza `AssignmentReasonRequiredError` (422) antes de cualquier lectura,
        `AssignmentNotFoundError`/`EventNotFoundError` (404) y
        `EventNotAssignableError` (409). Si ya estaba anulada devuelve la
        asignación sin nueva auditoría.
        """
        normalized_reason = _require_reason(reason)

        current = await self._assignments.get(assignment_id)
        if current is None:
            raise AssignmentNotFoundError()
        worker_id = current.worker_id

        await self._assignments.lock_worker(worker_id)
        assignment = await self._assignments.get_for_update(assignment_id)
        if assignment is None:
            raise AssignmentNotFoundError()

        event = await self._event_lookup(assignment.event_id)
        if event is None:
            raise EventNotFoundError()
        if event.status in _READ_ONLY_EVENT_STATUSES:
            raise EventNotAssignableError(event.status.value)

        if assignment.status is AssignmentStatus.CANCELLED:
            return assignment

        assignment.cancel()
        audit = AssignmentAudit.cancelled(
            assignment_id=assignment.id,
            actor_id=actor_id,
            occurred_at=self._clock.now(),
            reason=normalized_reason,
        )
        await self._assignments.save(assignment, audit)
        return assignment


def _require_reason(reason: object) -> str:
    """Exige un motivo no vacío antes de leer o bloquear nada (R-ASG-8, RN03)."""
    if not isinstance(reason, str) or not reason.strip():
        raise AssignmentReasonRequiredError()
    return reason.strip()


__all__ = ["CancelAssignment"]
