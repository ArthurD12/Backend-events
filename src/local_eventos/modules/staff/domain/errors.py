"""Errores del dominio de personal. `code` es estable para el frontend."""


class StaffValidationError(ValueError):
    """Dato inválido (responde 422). El texto dice qué dato falla; el `code` es siempre el mismo."""

    def __init__(self, message: str, code: str = "staff.validation") -> None:
        super().__init__(message)
        self.code = code


class StaffRuleError(Exception):
    """Operación no permitida por una regla del negocio (responde 409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
