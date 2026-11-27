"""Errores del dominio de personal (HU15/HU17).

`code` es estable para que el frontend lo traduzca. Python puro: no importa FastAPI,
SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

ASSIGNMENT_SCHEDULE_INVALID = "staff.assignment_schedule_invalid"
ASSIGNMENT_DATE_INVALID = "staff.assignment_date_invalid"
ASSIGNMENT_FUNCTION_REQUIRED = "staff.assignment_function_required"
ASSIGNMENT_PAY_INVALID = "staff.assignment_pay_invalid"
ASSIGNMENT_REASON_REQUIRED = "staff.assignment_reason_required"

UNAVAILABILITY_SCHEDULE_INVALID = "staff.unavailability_schedule_invalid"
UNAVAILABILITY_KIND_REQUIRED = "staff.unavailability_kind_required"
UNAVAILABILITY_WORKER_INVALID = "staff.unavailability_worker_invalid"
UNAVAILABILITY_DESCRIPTION_REQUIRED = "staff.unavailability_description_required"
UNAVAILABILITY_DESCRIPTION_NOT_ALLOWED = "staff.unavailability_description_not_allowed"
UNAVAILABILITY_DESCRIPTION_TOO_LONG = "staff.unavailability_description_too_long"
UNAVAILABILITY_REASON_REQUIRED = "staff.unavailability_reason_required"


class StaffValidationError(ValueError):
    """Dato de trabajador inválido (responde 422). `code` es estable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AssignmentScheduleInvalidError(StaffValidationError):
    """Horario de la asignación inválido (R-ASG-4): por ejemplo, fin igual a inicio."""

    def __init__(
        self, message: str = "El horario debe tener una hora de inicio y otra de fin distintas."
    ) -> None:
        super().__init__(ASSIGNMENT_SCHEDULE_INVALID, message)


class AssignmentDateInvalidError(StaffValidationError):
    """La fecha de la asignación no corresponde a la fecha del evento (Q5)."""

    def __init__(
        self, message: str = "La fecha de la asignación no corresponde a la fecha del evento."
    ) -> None:
        super().__init__(ASSIGNMENT_DATE_INVALID, message)


class AssignmentFunctionRequiredError(StaffValidationError):
    """No hay función en el cuerpo ni en la ficha del trabajador (R-ASG-17)."""

    def __init__(
        self,
        message: str = "Debe indicar la función para esta asignación.",
    ) -> None:
        super().__init__(ASSIGNMENT_FUNCTION_REQUIRED, message)


class AssignmentPayInvalidError(StaffValidationError):
    """El pago acordado no es un entero en céntimos mayor o igual a cero (R-ASG-7)."""

    def __init__(
        self,
        message: str = "El pago debe expresarse en céntimos enteros y no puede ser negativo.",
    ) -> None:
        super().__init__(ASSIGNMENT_PAY_INVALID, message)


class AssignmentReasonRequiredError(StaffValidationError):
    """La edición o la anulación de una asignación requiere motivo (R-ASG-8, RN03)."""

    def __init__(
        self,
        message: str = "La edición o la anulación de una asignación requiere motivo.",
    ) -> None:
        super().__init__(ASSIGNMENT_REASON_REQUIRED, message)


class UnavailabilityScheduleInvalidError(StaffValidationError):
    """Ventana de la indisponibilidad inválida (HU16): debe ser UTC y `end_at > start_at`."""

    def __init__(
        self, message: str = "La hora de fin debe ser posterior a la de inicio."
    ) -> None:
        super().__init__(UNAVAILABILITY_SCHEDULE_INVALID, message)


class UnavailabilityKindRequiredError(StaffValidationError):
    """La indisponibilidad no tiene un tipo válido (HU16, R-DIS-1)."""

    def __init__(
        self, message: str = "Debe indicar el tipo de indisponibilidad."
    ) -> None:
        super().__init__(UNAVAILABILITY_KIND_REQUIRED, message)


class UnavailabilityReasonRequiredError(StaffValidationError):
    """La edición o la anulación de una indisponibilidad requiere motivo (HU16, Q4)."""

    def __init__(
        self,
        message: str = "La edición o la anulación de una indisponibilidad requiere motivo.",
    ) -> None:
        super().__init__(UNAVAILABILITY_REASON_REQUIRED, message)
