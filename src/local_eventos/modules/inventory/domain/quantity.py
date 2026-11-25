"""Cantidades del almacén: `Decimal` con hasta 3 decimales (R-INV-1), como `numeric(12,3)`."""

from decimal import Decimal, InvalidOperation

from local_eventos.modules.inventory.domain.errors import InventoryValidationError

STEP = Decimal("0.001")
ZERO = Decimal("0.000")
_MAX = Decimal("999999999.999")  # numeric(12,3)


def to_quantity(value: Decimal | int | str) -> Decimal:
    """Valida y normaliza a 3 decimales. No redondea: más de 3 decimales es un error."""
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise InventoryValidationError("La cantidad no es un número válido.") from error
    if not number.is_finite():
        raise InventoryValidationError("La cantidad no es un número válido.")
    if number != number.quantize(STEP, rounding="ROUND_DOWN"):
        raise InventoryValidationError("La cantidad admite hasta 3 decimales.")
    if abs(number) > _MAX:
        raise InventoryValidationError("La cantidad es demasiado grande.")
    return number.quantize(STEP) + ZERO  # quita el signo de -0.000
