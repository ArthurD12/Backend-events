"""Forma de la asistencia en la API (HU18, T-10, plan §4.2/spec §7).

Solo describen la forma: enums, céntimos enteros, horas locales de `America/Lima`,
instantes UTC y el contrato de `event_code`/`event_date`/`event_status`
**anulables** cuando `commercial` no resuelve el evento (evento huérfano,
R-ATT-23): se devuelve la fila igualmente, nunca 404. Las reglas de negocio
(estado válido, motivo obligatorio solo en correcciones, ventana temporal) las
aplican el dominio y los casos de uso y llegan como 422/409 con su `staff.*`.

`AttendanceUpdate` acepta `status` vacío a propósito: el caso de uso responde
`staff.attendance_status_invalid` (no el 422 genérico de Pydantic). El enum se
documenta en OpenAPI con `json_schema_extra` para conservar el contrato.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from datetime import date as date_type
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from local_eventos.modules.commercial.public_api import EventInfo, EventStatus
from local_eventos.modules.staff.application.ports.attendance_repository import (
    AttendanceAssignmentView,
)
from local_eventos.modules.staff.domain.assignment_schedule import LIMA
from local_eventos.modules.staff.domain.attendance import AttendanceStatus
from local_eventos.modules.staff.domain.enums import AssignmentStatus, WorkerFunction


class AttendanceUpdate(BaseModel):
    """Cuerpo de `PATCH /v1/staff/assignments/{id}/attendance`.

    `status` es semánticamente obligatorio pero se declara opcional para que el
    caso de uso devuelva `staff.attendance_status_invalid` con su `code`.
    `reason` solo se exige cuando es una corrección; primer registro y mismo
    estado lo ignoran.
    """

    model_config = ConfigDict(extra="forbid")

    status: str | None = Field(
        default=None,
        description="ATTENDED o NOT_ATTENDED; la validación la hace el caso de uso",
        json_schema_extra={"enum": ["ATTENDED", "NOT_ATTENDED"]},
    )
    reason: str | None = Field(
        default=None,
        description=(
            "Motivo de la corrección; obligatorio solo al cambiar el estado "
            "(1..500 tras recortar). Se ignora en el primer registro y al repetir."
        ),
    )


class AttendanceOut(BaseModel):
    """Asignación con su asistencia vigente y el evento ya resuelto."""

    assignment_id: UUID
    worker_id: UUID
    worker_name: str
    event_id: UUID
    event_code: str | None
    event_status: EventStatus | None
    function: WorkerFunction
    function_description: str | None
    event_date: date_type | None
    start_time: time
    end_time: time
    start_at: datetime
    end_at: datetime
    pay_cents: int
    currency: Literal["PEN"]
    assignment_status: AssignmentStatus
    attendance_status: AttendanceStatus | None
    attendance_recorded_at: datetime | None
    attendance_recorded_by: str | None
    attendance_recorded_by_id: UUID | None

    @classmethod
    def from_parts(
        cls,
        *,
        assignment: AttendanceAssignmentView,
        attendance_status: AttendanceStatus | None,
        recorded_at: datetime | None,
        recorded_by: UUID | None,
        recorded_by_name: str | None,
        event: EventInfo | None,
    ) -> Self:
        """Mapea la asignación, la asistencia y el evento (anulable) a la respuesta.

        `event=None` deja `event_code`, `event_date` y `event_status` en `null`
        sin descartar la fila (R-ATT-23/CA-18.22). Las horas de la asignación se
        muestran en `America/Lima` y los instantes en UTC.
        """
        start_local = assignment.start_at.astimezone(LIMA)
        end_local = assignment.end_at.astimezone(LIMA)
        return cls(
            assignment_id=assignment.assignment_id,
            worker_id=assignment.worker_id,
            worker_name=assignment.worker_name,
            event_id=assignment.event_id,
            event_code=event.code if event is not None else None,
            event_status=event.status if event is not None else None,
            function=assignment.function,
            function_description=assignment.function_description,
            event_date=event.event_date if event is not None else None,
            start_time=start_local.time(),
            end_time=end_local.time(),
            start_at=assignment.start_at.astimezone(UTC),
            end_at=assignment.end_at.astimezone(UTC),
            pay_cents=assignment.pay_cents,
            currency="PEN",
            assignment_status=assignment.assignment_status,
            attendance_status=attendance_status,
            attendance_recorded_at=(
                recorded_at.astimezone(UTC) if recorded_at is not None else None
            ),
            attendance_recorded_by=recorded_by_name,
            attendance_recorded_by_id=recorded_by,
        )


class AttendanceHistoryPage(BaseModel):
    """Página del historial de asistencia de un trabajador."""

    items: list[AttendanceOut]
    total: int
    page: int
    page_size: int
