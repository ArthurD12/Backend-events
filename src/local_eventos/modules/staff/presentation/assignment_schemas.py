"""Forma de los datos de asignaciones en la API (HU17, plan §4.2).

Solo describen la forma: enums, céntimos enteros, fecha y horas locales de
`America/Lima` y el límite del motivo. Las reglas de negocio (estado del evento,
fecha válida, función obligatoria, solapes…) las aplican el dominio y los casos de
uso y llegan como 422/409 con su `staff.*`; aquí no se duplican.

`AssignmentUpdate` acepta `worker_id`/`event_id` a propósito: el router los usa
para responder 409 `staff.assignment_immutable` (el caso de uso no los usa), y
`extra="forbid"` rechaza cualquier otra clave del cuerpo.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from datetime import date as date_type
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from local_eventos.modules.commercial.public_api import EventStatus
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentView,
)
from local_eventos.modules.staff.domain.assignment_schedule import LIMA
from local_eventos.modules.staff.domain.enums import AssignmentStatus, WorkerFunction
from local_eventos.modules.staff.presentation.worker_schemas import Cents
from local_eventos.shared.presentation.problems import Problem

# Motivo de edición/anulación: obligatorio, recortado y 1..500 (plan §4.2/§10.7).
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class AssignmentCreate(BaseModel):
    """Cuerpo de `POST /v1/staff/assignments`: alta de una asignación."""

    event_id: UUID
    worker_id: UUID
    function: WorkerFunction | None = Field(
        default=None, description="Si se omite, se copia de la ficha del trabajador"
    )
    function_description: str | None = Field(
        default=None, max_length=120, description="Solo con la función OTHER"
    )
    date: date_type = Field(description="Fecha local de America/Lima")
    start_time: time = Field(description="Hora local de inicio")
    end_time: time = Field(description="Hora local de fin; si es menor, termina al día siguiente")
    pay_cents: Cents = Field(description="Pago acordado en céntimos: S/ 45.00 = 4500")


class AssignmentUpdate(BaseModel):
    """Cuerpo de `PUT /v1/staff/assignments/{id}`: reemplazo completo de los editables."""

    model_config = ConfigDict(extra="forbid")

    function: WorkerFunction = Field(description="Función de la asignación")
    function_description: str | None = Field(
        default=None, max_length=120, description="Solo con la función OTHER"
    )
    date: date_type = Field(description="Fecha local de America/Lima")
    start_time: time = Field(description="Hora local de inicio")
    end_time: time = Field(description="Hora local de fin; si es menor, termina al día siguiente")
    pay_cents: Cents = Field(description="Pago acordado en céntimos: S/ 45.00 = 4500")
    reason: Reason = Field(description="Motivo del cambio")
    # El router responde 409 si vienen; el caso de uso no los usa (plan §4.2).
    worker_id: UUID | None = Field(
        default=None, description="Inmutable; enviarlo responde staff.assignment_immutable"
    )
    event_id: UUID | None = Field(
        default=None, description="Inmutable; enviarlo responde staff.assignment_immutable"
    )


class AssignmentOut(BaseModel):
    """Asignación devuelta por la API: horario local, instantes UTC y pago."""

    id: UUID
    event_id: UUID
    event_code: str | None
    event_status: EventStatus | None
    worker_id: UUID
    worker_name: str
    function: WorkerFunction
    function_description: str | None
    date: date_type
    start_time: time
    end_time: time
    start_at: datetime
    end_at: datetime
    pay_cents: int
    currency: Literal["PEN"]
    status: AssignmentStatus

    @classmethod
    def from_view(cls, view: AssignmentView) -> Self:
        """Mapea la vista de aplicación a la respuesta, con fecha y horas en Lima."""
        start_local = view.start_at.astimezone(LIMA)
        end_local = view.end_at.astimezone(LIMA)
        return cls(
            id=view.id,
            event_id=view.event_id,
            event_code=view.event_code,
            event_status=view.event_status,
            worker_id=view.worker_id,
            worker_name=view.worker_name,
            function=view.function,
            function_description=view.function_description,
            date=start_local.date(),
            start_time=start_local.time(),
            end_time=end_local.time(),
            start_at=view.start_at.astimezone(UTC),
            end_at=view.end_at.astimezone(UTC),
            pay_cents=view.pay_cents,
            currency="PEN",
            status=view.status,
        )


class AssignmentListOut(BaseModel):
    """Listado de asignaciones de un evento."""

    items: list[AssignmentOut]


class AssignmentCancel(BaseModel):
    """Cuerpo de `POST /v1/staff/assignments/{id}/cancel`."""

    reason: Reason = Field(description="Motivo de la anulación")


class AssignmentConflictOut(BaseModel):
    """Conflicto de horario incluido en el 409, sin datos personales del trabajador."""

    event_code: str
    event_date: date_type
    start_time: time
    end_time: time


class AssignmentProblem(Problem):
    """Problem Details de asignaciones; documenta la extensión `conflicts` del 409."""

    conflicts: list[AssignmentConflictOut] = Field(default_factory=list)
