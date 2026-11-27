"""Errores de la capa de aplicación del personal (HU15/HU17).

`code` es estable para que el frontend y la API lo traduzcan (plan §2.4 y §4.4).
Python puro: no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from local_eventos.modules.staff.domain.document import Document


class StaffApplicationError(Exception):
    """Error de negocio de un caso de uso de personal. `code` es estable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DuplicateDocumentError(StaffApplicationError):
    """Ya existe otro trabajador —activo o inactivo— con el mismo tipo + número."""

    def __init__(self, document: Document) -> None:
        super().__init__(
            "staff.document_duplicated",
            f"Ya existe un trabajador con {document.type.value} {document.number}.",
        )


class WorkerNotFoundError(StaffApplicationError):
    """No hay ningún trabajador con el identificador solicitado."""

    def __init__(self) -> None:
        super().__init__(
            "staff.not_found",
            "No se encontró un trabajador con ese identificador.",
        )


class AssignmentNotFoundError(StaffApplicationError):
    """No hay ninguna asignación con el identificador solicitado."""

    def __init__(self) -> None:
        super().__init__(
            "staff.assignment_not_found",
            "No se encontró una asignación con ese identificador.",
        )


class EventNotFoundError(StaffApplicationError):
    """El evento referenciado no existe en `commercial`."""

    def __init__(self) -> None:
        super().__init__(
            "staff.event_not_found",
            "No se encontró un evento con ese identificador.",
        )


class WorkerInactiveError(StaffApplicationError):
    """El trabajador está inactivo y no admite asignaciones (CA-17.2)."""

    def __init__(self) -> None:
        super().__init__(
            "staff.worker_inactive",
            "El trabajador está inactivo y no se le pueden asignar eventos.",
        )


class EventNotAssignableError(StaffApplicationError):
    """El estado del evento no permite crear, editar ni anular asignaciones (CA-17.3/17.24)."""

    def __init__(self, status: str) -> None:
        super().__init__(
            "staff.event_not_assignable",
            f"El evento está en estado {status} y ya no admite cambios en sus asignaciones.",
        )


class AssignmentImmutableError(StaffApplicationError):
    """Se intentó cambiar el trabajador o el evento de una asignación existente (CA-17.15)."""

    def __init__(self) -> None:
        super().__init__(
            "staff.assignment_immutable",
            "El trabajador y el evento de una asignación no se pueden cambiar; "
            "anule la asignación y cree otra.",
        )


class WorkerHasFutureAssignmentsError(StaffApplicationError):
    """La baja del trabajador dejaría asignaciones futuras vigentes (CA-17.25)."""

    def __init__(self) -> None:
        super().__init__(
            "staff.worker_has_future_assignments",
            "El trabajador tiene asignaciones futuras vigentes; "
            "anule o edite esas asignaciones antes de darlo de baja.",
        )


@dataclass(frozen=True)
class AssignmentConflict:
    """Evento que se cruza con la asignación candidata, sin datos personales.

    Se compone en el caso de uso a partir de `AssignmentOverlap` y de la consulta
    de eventos; nunca expone documento, teléfono, tarifa ni pago (CA-17.10).
    """

    event_code: str
    event_date: date
    start_time: time
    end_time: time


class AssignmentOverlapError(StaffApplicationError):
    """El trabajador ya tiene asignaciones que se superponen con la ventana (CA-17.7/17.9/17.10).

    `conflicts` detalla código, fecha y horario de cada evento. Puede ir vacío
    cuando la restricción de exclusión de PostgreSQL rechaza una carrera y ya no
    es posible consultar los eventos en la transacción abortada (plan §5.5).
    """

    def __init__(self, conflicts: tuple[AssignmentConflict, ...] = ()) -> None:
        super().__init__(
            "staff.assignment_overlap",
            _overlap_message(conflicts),
        )
        self.conflicts = conflicts


def _overlap_message(conflicts: tuple[AssignmentConflict, ...]) -> str:
    if not conflicts:
        return "El trabajador ya tiene otra asignación que se superpone con ese horario."
    detalle = "; ".join(
        f"{conflict.event_code} del {conflict.event_date.strftime('%d/%m/%Y')} "
        f"de {conflict.start_time.strftime('%H:%M')} a {conflict.end_time.strftime('%H:%M')}"
        for conflict in conflicts
    )
    return f"El trabajador ya tiene asignaciones que se superponen: {detalle}."
