"""Caso de uso: editar una asignación existente (HU17, T-08, plan §3.2).

Flujo: el motivo es obligatorio desde el inicio; se lee la asignación sin bloqueo
para conocer el trabajador, se bloquea primero la fila del trabajador y después la
asignación (orden fijo para evitar deadlocks) y se relee. El evento debe existir y
seguir admitiendo cambios (`SCHEDULED`/`CONFIRMED`/`IN_PROGRESS`); `FINISHED` y
`CANCELLED` son de solo lectura (CA-17.24, R-ASG-18). La fecha solo se revalida
contra el evento si cambia el horario (Q5 y R-ASG-11): editar solo el pago o la
función no obliga a corregir la fecha aunque el evento se haya movido.

El trabajador inactivo solo bloquea si el nuevo `end_at` es futuro; corregir una
asignación pasada se permite. Antes de comprobar solapes se liberan los eventos
cancelados y el solape excluye la propia asignación (CA-17.14). Si no hay cambios
reales se devuelve la asignación sin escribir auditoría; si los hay, se escribe
`UPDATED` con motivo y snapshots anterior/nuevo (CA-17.13/17.18, R-ASG-8/9).

Python puro: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import time
from uuid import UUID

from local_eventos.modules.commercial.public_api import EventLookup, EventStatus
from local_eventos.modules.staff.application.assignment_occupancy import (
    AssignmentOccupancy,
)
from local_eventos.modules.staff.application.assignment_rules import (
    describe_conflicts,
    validate_event_date,
)
from local_eventos.modules.staff.application.errors import (
    AssignmentNotFoundError,
    AssignmentOverlapError,
    EventNotAssignableError,
    EventNotFoundError,
    WorkerInactiveError,
    WorkerNotFoundError,
)
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentRepository,
)
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerLookup,
)
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import (
    AssignmentAudit,
    AssignmentSnapshot,
)
from local_eventos.modules.staff.domain.assignment_schedule import AssignmentSchedule
from local_eventos.modules.staff.domain.enums import WorkerFunction, WorkerStatus
from local_eventos.modules.staff.domain.errors import AssignmentReasonRequiredError

_READ_ONLY_EVENT_STATUSES = frozenset({EventStatus.FINISHED, EventStatus.CANCELLED})


class UpdateAssignment:
    """Edita función, horario y pago de una asignación, auditando el cambio."""

    def __init__(
        self,
        assignments: AssignmentRepository,
        workers: WorkerLookup,
        event_lookup: EventLookup,
        occupancy: AssignmentOccupancy,
        clock: Clock,
    ) -> None:
        self._assignments = assignments
        self._workers = workers
        self._event_lookup = event_lookup
        self._occupancy = occupancy
        self._clock = clock

    async def execute(
        self,
        *,
        assignment_id: UUID,
        function: WorkerFunction,
        function_description: str | None,
        date: date_type,
        start_time: time,
        end_time: time,
        pay_cents: int,
        reason: str,
        actor_id: UUID,
    ) -> Assignment:
        """Edita la asignación y devuelve el agregado persistido.

        Lanza `AssignmentReasonRequiredError` (422) antes de cualquier lectura,
        `AssignmentNotFoundError`/`EventNotFoundError` (404), y
        `EventNotAssignableError`/`WorkerInactiveError`/`AssignmentOverlapError`
        (409). Un no-op devuelve la asignación sin auditoría.
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

        schedule = AssignmentSchedule(date=date, start_time=start_time, end_time=end_time)
        if schedule.start_at != assignment.start_at or schedule.end_at != assignment.end_at:
            validate_event_date(
                assignment_date=date,
                event_date=event.event_date,
                event_start_time=event.start_time,
                event_end_time=event.end_time,
            )

        worker = await self._workers.get(assignment.worker_id)
        if worker is None:
            raise WorkerNotFoundError()
        if worker.status is not WorkerStatus.ACTIVE and schedule.end_at > self._clock.now():
            raise WorkerInactiveError()

        await self._occupancy.release_cancelled(worker_id)
        overlaps = await self._assignments.list_active_overlaps(
            worker_id,
            schedule.start_at,
            schedule.end_at,
            exclude_assignment_id=assignment.id,
        )
        if overlaps:
            raise AssignmentOverlapError(await describe_conflicts(self._event_lookup, overlaps))

        previous = AssignmentSnapshot.from_mapping(assignment.snapshot())
        changed = assignment.update(
            function=function,
            function_description=function_description,
            start_at=schedule.start_at,
            end_at=schedule.end_at,
            pay=pay_cents,
        )
        if not changed:
            return assignment

        new = AssignmentSnapshot.from_mapping(assignment.snapshot())
        audit = AssignmentAudit.updated(
            assignment_id=assignment.id,
            actor_id=actor_id,
            occurred_at=self._clock.now(),
            reason=normalized_reason,
            previous_values=previous,
            new_values=new,
        )
        await self._assignments.save(assignment, audit)
        return assignment


def _require_reason(reason: object) -> str:
    """Exige un motivo no vacío antes de leer o bloquear nada (R-ASG-8, RN03)."""
    if not isinstance(reason, str) or not reason.strip():
        raise AssignmentReasonRequiredError()
    return reason.strip()


__all__ = ["UpdateAssignment"]
