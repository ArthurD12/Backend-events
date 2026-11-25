"""Errores del dominio de personal (HU15/HU17).

`code` es estable para que el frontend lo traduzca. Python puro: no importa FastAPI,
SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

ASSIGNMENT_SCHEDULE_INVALID = "staff.assignment_schedule_invalid"
ASSIGNMENT_DATE_INVALID = "staff.assignment_date_invalid"
ASSIGNMENT_FUNCTION_REQUIRED = "staff.assignment_function_required"
ASSIGNMENT_PAY_INVALID = "staff.assignment_pay_invalid"


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
