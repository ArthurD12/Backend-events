"""Errores de dominio de la asistencia del personal (HU18, R-ATT-2/R-ATT-22).

`code` es estable para que el frontend lo traduzca. Heredan de
`StaffValidationError` para responder 422 con el mismo formato que el resto del
módulo. Python puro: no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from local_eventos.modules.staff.domain.errors import StaffValidationError

ATTENDANCE_STATUS_INVALID = "staff.attendance_status_invalid"
ATTENDANCE_REASON_REQUIRED = "staff.attendance_reason_required"

REASON_MAX_LENGTH = 500


class AttendanceStatusInvalidError(StaffValidationError):
    """El estado de asistencia falta o no es `ATTENDED`/`NOT_ATTENDED` (R-ATT-2)."""

    def __init__(
        self,
        message: str = "El estado de asistencia debe ser ATTENDED o NOT_ATTENDED.",
    ) -> None:
        super().__init__(ATTENDANCE_STATUS_INVALID, message)


class AttendanceReasonRequiredError(StaffValidationError):
    """Una corrección de asistencia exige motivo recortado de 1 a 500 caracteres (R-ATT-22)."""

    def __init__(
        self,
        message: str = "La corrección de asistencia requiere un motivo de 1 a 500 caracteres.",
    ) -> None:
        super().__init__(ATTENDANCE_REASON_REQUIRED, message)
