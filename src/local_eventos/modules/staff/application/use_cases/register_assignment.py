"""Caso de uso: asignar un trabajador a un evento (HU17, T-07, plan §3.1).

Flujo: el evento debe existir y admitir cambios (`SCHEDULED`/`CONFIRMED`/
`IN_PROGRESS`), el trabajador debe existir y estar `ACTIVE`, la fecha debe ser la
del evento (o la siguiente si el evento cruza medianoche, Q5) y la función se copia
de la ficha si el cuerpo la omite. Antes de crear la asignación se bloquea la fila
del trabajador, se liberan las asignaciones de eventos cancelados y se comprueban
los solapes para devolver un 409 con el código, la fecha y el horario de cada
evento en conflicto (nunca datos personales).

La auditoría `CREATED` se escribe en la misma transacción que la asignación. El
evento se consulta solo por `commercial.public_api` (R-ASG-13). Python puro: sin
FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
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
from local_eventos.modules.staff.domain.assignment_audit import AssignmentAudit
from local_eventos.modules.staff.domain.assignment_schedule import AssignmentSchedule
from local_eventos.modules.staff.domain.enums import WorkerFunction, WorkerStatus
from local_eventos.modules.staff.domain.errors import AssignmentFunctionRequiredError

_ASSIGNABLE_EVENT_STATUSES = frozenset(
    {EventStatus.SCHEDULED, EventStatus.CONFIRMED, EventStatus.IN_PROGRESS}
)


class RegisterAssignment:
    """Registra una asignación activa, audita el alta y libera cancelados previos."""

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
        event_id: UUID,
        worker_id: UUID,
        function: WorkerFunction | None,
        function_description: str | None,
        date: date_type,
        start_time: time,
        end_time: time,
        pay_cents: int,
        actor_id: UUID,
    ) -> Assignment:
        """Crea la asignación y devuelve el agregado persistido.

        Lanza `EventNotFoundError`/`WorkerNotFoundError` (404), `EventNotAssignableError`/
        `WorkerInactiveError`/`AssignmentOverlapError` (409) y los errores de
        validación del dominio (422).
        """
        event = await self._event_lookup(event_id)
        if event is None:
            raise EventNotFoundError()
        if event.status not in _ASSIGNABLE_EVENT_STATUSES:
            raise EventNotAssignableError(event.status.value)

        worker = await self._workers.get(worker_id)
        if worker is None:
            raise WorkerNotFoundError()
        if worker.status is not WorkerStatus.ACTIVE:
            raise WorkerInactiveError()

        schedule = AssignmentSchedule(date=date, start_time=start_time, end_time=end_time)
        validate_event_date(
            assignment_date=date,
            event_date=event.event_date,
            event_start_time=event.start_time,
            event_end_time=event.end_time,
        )

        resolved_function, resolved_description = _resolve_function(
            function=function,
            function_description=function_description,
            worker_function=worker.function,
            worker_function_description=worker.function_description,
        )

        await self._assignments.lock_worker(worker_id)
        await self._occupancy.release_cancelled(worker_id)

        overlaps = await self._assignments.list_active_overlaps(
            worker_id, schedule.start_at, schedule.end_at
        )
        if overlaps:
            raise AssignmentOverlapError(await describe_conflicts(self._event_lookup, overlaps))

        assignment = Assignment.register(
            event_id=event_id,
            worker_id=worker_id,
            function=resolved_function,
            function_description=resolved_description,
            start_at=schedule.start_at,
            end_at=schedule.end_at,
            pay=pay_cents,
        )
        audit = AssignmentAudit.created(
            assignment_id=assignment.id,
            actor_id=actor_id,
            occurred_at=self._clock.now(),
        )
        await self._assignments.save(assignment, audit)
        return assignment


def _resolve_function(
    *,
    function: WorkerFunction | None,
    function_description: str | None,
    worker_function: WorkerFunction | None,
    worker_function_description: str | None,
) -> tuple[WorkerFunction, str | None]:
    """Usa la función enviada o copia la de la ficha; la ficha no se modifica.

    Si el cuerpo la omite y la ficha tampoco tiene, lanza
    `staff.assignment_function_required` antes de bloquear o comprobar solapes
    (R-ASG-17, plan §3.1).
    """
    if function is not None:
        return function, function_description
    if worker_function is None:
        raise AssignmentFunctionRequiredError()
    return worker_function, worker_function_description


__all__ = ["RegisterAssignment"]
