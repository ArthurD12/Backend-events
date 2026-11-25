"""Errores del dominio de inventario. `code` es estable para que el frontend lo traduzca."""

from decimal import Decimal


class InventoryValidationError(ValueError):
    """Dato inválido (responde 422 con `inventory.validation`)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "inventory.validation"


class InventoryRuleError(Exception):
    """Operación no permitida por una regla del almacén (responde 409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class InsufficientStockError(InventoryRuleError):
    """RN20: no se saca más de lo que hay. Lleva el disponible para mostrarlo."""

    def __init__(self, available: Decimal) -> None:
        super().__init__(
            "inventory.insufficient_stock",
            f"Stock insuficiente: solo hay {available} disponible.",
        )
        self.available = available
