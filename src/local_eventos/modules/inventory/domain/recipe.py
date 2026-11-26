"""Insumos de un servicio del catálogo (HU24): producto, cantidad y base de cálculo.

La receta se guarda entera y reemplaza a la anterior (CA-24.3). Python puro: no importa
FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum
from uuid import UUID

from local_eventos.modules.inventory.domain.errors import InventoryValidationError
from local_eventos.modules.inventory.domain.quantity import STEP, ZERO, to_quantity

MAX_RECIPE_LINES = 100


class RecipeBasis(StrEnum):
    PER_PERSON = "PER_PERSON"  # por invitado del evento
    PER_SERVICE = "PER_SERVICE"  # una vez por cada unidad contratada del servicio


@dataclass(frozen=True)
class RecipeLine:
    product_id: UUID
    quantity: Decimal
    basis: RecipeBasis

    def required_for(self, *, guests: int, contracted: int) -> Decimal:
        """Cantidad para el evento; hacia arriba a 3 decimales (R-REC-1)."""
        factor = guests if self.basis is RecipeBasis.PER_PERSON else contracted
        return (self.quantity * factor).quantize(STEP, rounding=ROUND_CEILING) + ZERO


def clean_recipe(lines: list[RecipeLine]) -> list[RecipeLine]:
    """CA-24.2: cantidades válidas y un producto una sola vez por servicio."""
    if len(lines) > MAX_RECIPE_LINES:
        raise InventoryValidationError(f"Una receta admite hasta {MAX_RECIPE_LINES} insumos.")
    cleaned = []
    for line in lines:
        amount = to_quantity(line.quantity)
        if amount <= 0:
            raise InventoryValidationError("La cantidad del insumo debe ser mayor que cero.")
        cleaned.append(RecipeLine(line.product_id, amount, RecipeBasis(line.basis)))
    if len({line.product_id for line in cleaned}) != len(cleaned):
        raise InventoryValidationError("Un producto aparece dos veces en la receta.")
    return cleaned
