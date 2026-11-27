"""Forma de los datos de disponibilidad en la API (HU16, plan §4.3).

Solo describen la forma del contrato: enums, fechas y horas locales de
`America/Lima` en la entrada, instantes UTC en los campos `*_at` y límites de
motivo/descripción. Las reglas de negocio (ventana válida, máximo 31 días,
horario, tipo/descripción) las validan el dominio y los casos de uso y llegan
como 422/409 con su `staff.*`; aquí no se duplican.

Privacidad (R-DIS-9, CA-16.8): la respuesta se construye con estos DTOs y nunca
incluye pago, tarifa, documento ni teléfono. Un test recorre todas las claves de
`AvailabilityOut` para impedir que se filtren.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from datetime import date as date_type
from typing import Annotated, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from local_eventos.modules.staff.application.use_cases.get_staff_availability import (
    AvailabilityItem as _AvailabilityItem,
)
from local_eventos.modules.staff.application.use_cases.get_staff_availability import (
    AvailabilityReport,
)
from local_eventos.modules.staff.domain.enums import (
    AvailabilityState,
    UnavailabilityKind,
    UnavailabilityStatus,
    WorkerFunction,
)
from local_eventos.modules.staff.domain.lima import utc_to_local
from local_eventos.modules.staff.domain.unavailability import Unavailability

# Motivo de edición/anulación: obligatorio, recortado y 1..500 (plan §4.3/§11.9).
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
# Descripción de `OTHER`: obligatoria en ese tipo, máximo 120 (plan §2.1).
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


def _ensure_utc(value: datetime) -> datetime:
    """Exige un instante con zona y lo normaliza a UTC (salida de la API)."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("El instante debe incluir zona horaria.")
    return value.astimezone(UTC)


def _ensure_local_time(value: time) -> time:
    """Exige una hora local sin zona; la conversión Lima → UTC la hace el dominio."""
    if value.tzinfo is not None:
        raise ValueError("La hora debe ser local de America/Lima, sin zona.")
    return value


UtcDateTime = Annotated[datetime, AfterValidator(_ensure_utc)]
LocalTime = Annotated[time, AfterValidator(_ensure_local_time)]


class _Schema(BaseModel):
    """Base de los esquemas de disponibilidad: rechaza claves desconocidas."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AvailabilityConflict(_Schema):
    """Asignación que ocupa parte de la ventana, sin datos sensibles (R-DIS-9).

    Solo código y fecha del evento, horario local de la asignación y su función.
    Nunca pago, tarifa, documento ni teléfono (CA-16.8). `event_code` y
    `event_date` son `None` cuando la asignación ocupa pero su evento no existe;
    las horas siempre están presentes porque salen de la asignación.
    """

    event_code: str | None
    event_date: date_type | None
    start_time: LocalTime
    end_time: LocalTime
    function: WorkerFunction | None
    function_description: str | None


class UnavailabilityDetail(_Schema):
    """Indisponibilidad activa que explica un estado `UNAVAILABLE` (CA-16.9)."""

    id: UUID
    kind: UnavailabilityKind
    description: str | None
    start_at: UtcDateTime
    end_at: UtcDateTime


class AvailabilityItem(_Schema):
    """Disponibilidad de un trabajador en la ventana consultada."""

    worker_id: UUID
    name: str
    function: WorkerFunction | None
    function_description: str | None
    state: AvailabilityState
    conflicts: list[AvailabilityConflict]
    unavailabilities: list[UnavailabilityDetail]

    @classmethod
    def from_item(cls, item: _AvailabilityItem) -> Self:
        """Mapea el resultado del caso de uso a la respuesta de la API."""
        return cls(
            worker_id=item.worker_id,
            name=item.name,
            function=item.function,
            function_description=item.function_description,
            state=item.state,
            conflicts=[
                AvailabilityConflict(
                    event_code=conflict.event_code,
                    event_date=conflict.event_date,
                    start_time=conflict.start_time,
                    end_time=conflict.end_time,
                    function=conflict.function,
                    function_description=conflict.function_description,
                )
                for conflict in item.conflicts
            ],
            unavailabilities=[
                UnavailabilityDetail(
                    id=detail.id,
                    kind=detail.kind,
                    description=detail.description,
                    start_at=detail.start_at,
                    end_at=detail.end_at,
                )
                for detail in item.unavailabilities
            ],
        )


class AvailabilityOut(_Schema):
    """Respuesta de `GET /v1/staff/availability`: ventana UTC y lista plana."""

    from_: UtcDateTime = Field(alias="from", description="Inicio UTC de la ventana (exclusivo)")
    to: UtcDateTime = Field(description="Fin UTC de la ventana (exclusivo)")
    items: list[AvailabilityItem]

    @classmethod
    def from_report(cls, report: AvailabilityReport) -> Self:
        """Mapea el informe del caso de uso, conservando la ventana en UTC."""
        return cls(
            from_=report.start_at,
            to=report.end_at,
            items=[AvailabilityItem.from_item(item) for item in report.items],
        )


class UnavailabilityCreate(_Schema):
    """Cuerpo de `POST /v1/staff/unavailability`: alta con fecha y horas locales."""

    worker_id: UUID
    date: date_type = Field(description="Fecha local de America/Lima")
    start_time: LocalTime = Field(description="Hora local de inicio")
    end_time: LocalTime = Field(
        description="Hora local de fin; si es menor, termina al día siguiente"
    )
    kind: UnavailabilityKind
    description: Description | None = Field(
        default=None, description="Obligatoria solo con el tipo OTHER"
    )


class UnavailabilityUpdate(_Schema):
    """Cuerpo de `PUT /v1/staff/unavailability/{id}`: reemplazo de los editables."""

    kind: UnavailabilityKind
    description: Description | None = Field(
        default=None, description="Obligatoria solo con el tipo OTHER"
    )
    date: date_type = Field(description="Fecha local de America/Lima")
    start_time: LocalTime = Field(description="Hora local de inicio")
    end_time: LocalTime = Field(
        description="Hora local de fin; si es menor, termina al día siguiente"
    )
    reason: Reason = Field(description="Motivo del cambio")


class UnavailabilityCancel(_Schema):
    """Cuerpo de `POST /v1/staff/unavailability/{id}/cancel`."""

    reason: Reason = Field(description="Motivo de la anulación")


class UnavailabilityOut(_Schema):
    """Indisponibilidad devuelta por la API: fecha/horas locales e instantes UTC."""

    # Sin created_at/updated_at: el agregado de dominio no los tiene y la fuente
    # real de "quién y cuándo" es la auditoría del módulo.
    id: UUID
    worker_id: UUID
    kind: UnavailabilityKind
    description: str | None
    date: date_type
    start_time: LocalTime
    end_time: LocalTime
    start_at: UtcDateTime
    end_at: UtcDateTime
    status: UnavailabilityStatus

    @classmethod
    def from_unavailability(cls, item: Unavailability) -> Self:
        """Mapea el agregado a la respuesta, con fecha y horas en Lima."""
        start_local = utc_to_local(item.start_at)
        end_local = utc_to_local(item.end_at)
        return cls(
            id=item.id,
            worker_id=item.worker_id,
            kind=item.kind,
            description=item.description,
            date=start_local.date(),
            start_time=start_local.time(),
            end_time=end_local.time(),
            start_at=item.start_at,
            end_at=item.end_at,
            status=item.status,
        )


class UnavailabilityListOut(_Schema):
    """Listado de indisponibilidades (incluye las anuladas)."""

    items: list[UnavailabilityOut]
