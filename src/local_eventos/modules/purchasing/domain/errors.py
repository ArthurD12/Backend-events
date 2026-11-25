"""Errores del dominio de compras. `code` es estable para que el frontend lo traduzca."""


class PurchasingValidationError(ValueError):
    """Dato inválido (responde 422 con `purchasing.validation`)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "purchasing.validation"


class PurchasingRuleError(Exception):
    """Operación no permitida (responde 409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class InvalidTransitionError(PurchasingRuleError):
    """RN21: solicitada → ordenada → recibida | cancelada. Recibida o cancelada no cambia."""

    def __init__(self, message: str) -> None:
        super().__init__("purchasing.invalid_transition", message)
