"""Errores de aplicación de la asistencia del personal (HU18).

`code` es estable para que el frontend y la API lo traduzcan (plan §2.4/§4.3).
Heredan de `StaffApplicationError` para que presentación los mapee con un único
handler. Reutiliza `AssignmentNotFoundError` de HU17: no se duplica el string.
No existe `staff.event_not_found`: un evento huérfano se devuelve con los campos
en `null` (R-ATT-23). Python puro: sin FastAPI, SQLAlchemy ni Pydantic.

Los errores de validación del estado y del motivo viven en el dominio
(`domain/attendance_errors.py`) y responden 422 con su propio `code`.
"""

from __future__ import annotations

from local_eventos.modules.staff.application.errors import (
    AssignmentNotFoundError,
    StaffApplicationError,
)

ATTENDANCE_WORKER_NOT_FOUND = "staff.worker_not_found"
ATTENDANCE_NOT_DUE = "staff.attendance_not_due"
ATTENDANCE_ASSIGNMENT_CANCELLED = "staff.attendance_assignment_cancelled"
ATTENDANCE_DATE_RANGE_INVALID = "staff.attendance_date_range_invalid"

__all__ = [
    "ATTENDANCE_ASSIGNMENT_CANCELLED",
    "ATTENDANCE_DATE_RANGE_INVALID",
    "ATTENDANCE_NOT_DUE",
    "ATTENDANCE_WORKER_NOT_FOUND",
    "AssignmentNotFoundError",
    "AttendanceAssignmentCancelledError",
    "AttendanceDateRangeInvalidError",
    "AttendanceNotDueError",
    "AttendanceWorkerNotFoundError",
]


class AttendanceWorkerNotFoundError(StaffApplicationError):
    """No hay ningún trabajador con el identificador solicitado (R-ATT-19)."""

    def __init__(self) -> None:
        super().__init__(
            ATTENDANCE_WORKER_NOT_FOUND,
            "No se encontró un trabajador con ese identificador.",
        )


class AttendanceNotDueError(StaffApplicationError):
    """La asignación aún no termina y no admite registro de asistencia (R-ATT-5)."""

    def __init__(self) -> None:
        super().__init__(
            ATTENDANCE_NOT_DUE,
            "La asignación aún no ha terminado; registre la asistencia al finalizar.",
        )


class AttendanceAssignmentCancelledError(StaffApplicationError):
    """La asignación está anulada y no admite asistencia (R-ATT-4/R-ATT-21)."""

    def __init__(self) -> None:
        super().__init__(
            ATTENDANCE_ASSIGNMENT_CANCELLED,
            "La asignación está anulada y no admite registro de asistencia.",
        )


class AttendanceDateRangeInvalidError(StaffApplicationError):
    """El rango de fechas o la paginación del historial están fuera de rango (R-ATT-10)."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            ATTENDANCE_DATE_RANGE_INVALID,
            message or "El rango de fechas o la paginación del historial no son válidos.",
        )
