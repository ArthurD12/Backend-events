"""Caso de uso: registrar o corregir la asistencia de una asignación (HU18, T-03, plan §3.1).

Flujo (en este orden):

1. Se bloquea la asignación con `lock_assignment` (`SELECT ... FOR UPDATE`); si no
   existe → 404 `staff.assignment_not_found`.
2. Asignación `CANCELLED` → 409 `staff.attendance_assignment_cancelled` **antes**
   de mirar la ventana temporal (R-ATT-4/R-ATT-21).
3. `now = clock.now()` en UTC; `now < end_at` → 409 `staff.attendance_not_due`.
   `now == end_at` se acepta (R-ATT-5, CA-18.1).
4. Se valida el estado: ausente o distinto de `ATTENDED`/`NOT_ATTENDED` → 422
   `staff.attendance_status_invalid`.
5. Se resuelve el evento con `commercial.public_api.event_lookup` de forma
   **tolerante**: un evento huérfano deja `event=None` (campos `null` en la
   respuesta), sin 404 ni excepción (R-ATT-23/CA-18.22).
6. Se lee el estado vigente:
   - sin registro → primer `RECORDED` (el motivo se ignora);
   - mismo estado → idempotente, sin motivo ni auditoría (R-ATT-17/CA-18.12);
   - estado distinto → exige motivo 1..500 y audita `CORRECTED` (R-ATT-22).
7. Se devuelve la vista de asignación, la asistencia vigente y el evento resuelto.

No modifica la asignación, el horario, el pago, la disponibilidad ni el ledger
(R-ATT-15/R-ATT-19). Python puro: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from uuid import UUID

from local_eventos.modules.commercial.public_api import EventInfo, EventLookup
from local_eventos.modules.staff.application.attendance_errors import (
    AttendanceAssignmentCancelledError,
    AttendanceNotDueError,
)
from local_eventos.modules.staff.application.errors import AssignmentNotFoundError
from local_eventos.modules.staff.application.ports.attendance_repository import (
    AttendanceAssignmentView,
    AttendanceRepository,
    AttendanceView,
)
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.domain.attendance import Attendance, AttendanceStatus
from local_eventos.modules.staff.domain.attendance_errors import AttendanceStatusInvalidError
from local_eventos.modules.staff.domain.enums import AssignmentStatus

__all__ = ["AttendanceUpdateResult", "UpdateAttendance"]


@dataclass(frozen=True)
class AttendanceUpdateResult:
    """Resultado del registro/corrección: asignación, asistencia vigente y evento.

    `event=None` cuando `commercial` no resuelve el `event_id` (evento huérfano):
    es un resultado válido, no un 404 (R-ATT-23/CA-18.22).
    """

    assignment: AttendanceAssignmentView
    attendance: AttendanceView
    event: EventInfo | None


class UpdateAttendance:
    """Registra el primer estado de asistencia o corrige el vigente, auditando."""

    def __init__(
        self,
        attendance: AttendanceRepository,
        event_lookup: EventLookup,
        clock: Clock,
    ) -> None:
        self._attendance = attendance
        self._event_lookup = event_lookup
        self._clock = clock

    async def execute(
        self,
        *,
        assignment_id: UUID,
        status: AttendanceStatus | str | None,
        reason: str | None,
        actor_id: UUID,
    ) -> AttendanceUpdateResult:
        """Registra o corrige la asistencia y devuelve el estado vigente.

        Lanza `AssignmentNotFoundError` (404), `AttendanceAssignmentCancelledError`
        y `AttendanceNotDueError` (409), y `AttendanceStatusInvalidError` /
        `AttendanceReasonRequiredError` (422).
        """
        assignment = await self._attendance.lock_assignment(assignment_id)
        if assignment is None:
            raise AssignmentNotFoundError()

        if assignment.assignment_status is AssignmentStatus.CANCELLED:
            raise AttendanceAssignmentCancelledError()

        now = self._clock.now().astimezone(UTC)
        if now < assignment.end_at:
            raise AttendanceNotDueError()

        target = _require_status(status)

        event = await self._event_lookup(assignment.event_id)

        current = await self._attendance.get(assignment_id)
        if current is None:
            recorded, audit = Attendance.record(
                assignment_id=assignment_id,
                status=target,
                actor_id=actor_id,
                recorded_at=now,
            )
            await self._attendance.save(recorded, audit)
            return AttendanceUpdateResult(
                assignment=assignment,
                attendance=_view(recorded),
                event=event,
            )

        if current.status is target:
            return AttendanceUpdateResult(
                assignment=assignment,
                attendance=current,
                event=event,
            )

        corrected = Attendance(
            assignment_id=current.assignment_id,
            status=current.status,
            recorded_by=current.recorded_by,
            recorded_at=current.recorded_at,
        )
        correction = corrected.correct(
            new_status=target,
            reason=reason,
            actor_id=actor_id,
            occurred_at=now,
        )
        # `correct` solo devuelve `None` si el estado no cambia, ya descartado arriba.
        if correction is None:  # pragma: no cover - invariante del agregado
            raise RuntimeError("La corrección de asistencia debía generar una auditoría.")
        await self._attendance.save(corrected, correction)
        return AttendanceUpdateResult(
            assignment=assignment,
            attendance=_view(corrected),
            event=event,
        )


def _require_status(value: AttendanceStatus | str | None) -> AttendanceStatus:
    """Acepta el enum o su texto exacto; cualquier otro valor es 422 (R-ATT-2)."""
    if isinstance(value, AttendanceStatus):
        return value
    if isinstance(value, str):
        try:
            return AttendanceStatus(value)
        except ValueError:
            raise AttendanceStatusInvalidError() from None
    raise AttendanceStatusInvalidError()


def _view(attendance: Attendance) -> AttendanceView:
    return AttendanceView(
        assignment_id=attendance.assignment_id,
        status=attendance.status,
        recorded_by=attendance.recorded_by,
        recorded_at=attendance.recorded_at,
    )
