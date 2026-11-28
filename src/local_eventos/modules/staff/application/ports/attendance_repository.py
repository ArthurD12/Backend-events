"""Puerto del repositorio de asistencia (HU18, R-ATT-4/R-ATT-5/R-ATT-19/R-ATT-23).

La aplicación usa este contrato y la infraestructura lo implementa. En esta capa
solo hay stdlib y `typing`: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).

Los DTO son vistas de lectura inmutables. El repositorio no resuelve el evento:
`event_id` viaja como referencia y la aplicación lo completa con
`commercial.public_api.event_lookup`; si el evento no se resuelve (huérfano) se
devuelve `null` sin descartar la fila (R-ATT-23).

`save` persiste el estado vigente y su auditoría en la **misma transacción**
(plan §5.3): si la auditoría falla, el estado no queda.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from local_eventos.modules.staff.domain.attendance import Attendance, AttendanceStatus
from local_eventos.modules.staff.domain.attendance_audit import AttendanceAudit
from local_eventos.modules.staff.domain.enums import AssignmentStatus, WorkerFunction


@dataclass(frozen=True)
class AttendanceAssignmentView:
    """Asignación de solo lectura con el nombre del trabajador y el pago acordado.

    `start_at`/`end_at` están en UTC aware. `event_id` es una referencia a
    `commercial`, sin FK; la aplicación la resuelve por `public_api` y deja los
    campos del evento en `None` si es huérfano (R-ATT-23).
    """

    assignment_id: UUID
    event_id: UUID
    worker_id: UUID
    worker_name: str
    function: WorkerFunction
    function_description: str | None
    start_at: datetime
    end_at: datetime
    pay_cents: int
    currency: str
    assignment_status: AssignmentStatus


@dataclass(frozen=True)
class AttendanceHistoryRow(AttendanceAssignmentView):
    """Fila del historial: la asignación más su asistencia vigente, si existe.

    `attendance_status=None` significa "sin registrar" y no debe confundirse con
    una falta (R-ATT-3/R-ATT-21). `recorded_at`/`recorded_by` son nulos cuando no
    hay registro o la asignación está `CANCELLED`.
    """

    attendance_status: AttendanceStatus | None = None
    recorded_at: datetime | None = None
    recorded_by: UUID | None = None


@dataclass(frozen=True)
class AttendanceView:
    """Estado vigente de la asistencia de una asignación, sin el agregado mutable."""

    assignment_id: UUID
    status: AttendanceStatus
    recorded_by: UUID
    recorded_at: datetime


class AttendanceRepository(Protocol):
    """Operaciones que necesitan los casos de uso de asistencia."""

    async def lock_assignment(self, assignment_id: UUID) -> AttendanceAssignmentView | None:
        """Lee la asignación bloqueando la fila hasta el fin de la transacción.

        Emite `SELECT ... FOR UPDATE` sobre `staff_assignments` y su trabajador
        (plan §5.3), de modo que correcciones simultáneas se serialicen. Si la
        asignación no existe devuelve `None` (404 `staff.assignment_not_found`).
        """
        ...

    async def get(self, assignment_id: UUID) -> AttendanceView | None:
        """Estado vigente de la asignación, o `None` si todavía no hay registro."""
        ...

    async def save(self, attendance: Attendance, audit: AttendanceAudit) -> None:
        """Inserta o actualiza el estado vigente y escribe la auditoría en la misma transacción."""
        ...

    async def list_history(
        self,
        worker_id: UUID,
        event_id: UUID | None = None,
    ) -> list[AttendanceHistoryRow]:
        """Historial del trabajador, una fila por asignación `ACTIVE` o `CANCELLED`.

        Incluye trabajadores inactivos, ordena por `start_at DESC` y aplica el
        filtro `event_id` en SQL. La asistencia se une con `LEFT JOIN`: las filas
        sin registro llegan con `attendance_status=None` (R-ATT-9/R-ATT-11/R-ATT-21).
        """
        ...
