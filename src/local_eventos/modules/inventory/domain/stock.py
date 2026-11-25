"""Existencias de un producto (HU23): cantidad y costo promedio ponderado (R-INV-3).

El stock es la suma de los movimientos; `apply` lo actualiza movimiento a movimiento y nunca
lo deja negativo (RN20). La base lo garantiza además con un CHECK y un bloqueo de fila.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from local_eventos.modules.inventory.domain.errors import InsufficientStockError
from local_eventos.modules.inventory.domain.movement import Movement, MovementKind
from local_eventos.modules.inventory.domain.quantity import ZERO

EXPIRY_WARNING_DAYS = 15  # R-INV-4


@dataclass(frozen=True)
class StockLevel:
    product_id: UUID
    quantity: Decimal = ZERO
    avg_cost_cents: int = 0

    def apply(self, movement: Movement) -> StockLevel:
        """Devuelve el stock después del movimiento. Falla si quedaría negativo."""
        if movement.product_id != self.product_id:
            raise ValueError("El movimiento es de otro producto.")
        new_quantity = self.quantity + movement.stock_delta
        if new_quantity < 0:
            raise InsufficientStockError(self.quantity)
        avg = self.avg_cost_cents
        if movement.kind is MovementKind.ENTRY and movement.unit_cost_cents is not None:
            if self.quantity <= 0:
                avg = movement.unit_cost_cents
            else:
                total = self.quantity * avg + movement.quantity * movement.unit_cost_cents
                avg = int((total / new_quantity).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        return replace(self, quantity=new_quantity, avg_cost_cents=avg)

    @property
    def value_cents(self) -> int:
        """Valor del stock al costo promedio, en céntimos."""
        return int((self.quantity * self.avg_cost_cents).quantize(Decimal(1), ROUND_HALF_UP))


def is_low_stock(quantity: Decimal, min_stock: Decimal) -> bool:
    """CA-23.5: stock bajo cuando no supera el mínimo."""
    return quantity <= min_stock


def next_expiry(quantity: Decimal, entries: list[Movement]) -> date | None:
    """Vencimiento más cercano de las entradas que aún tienen stock (CA-23.5).

    Las salidas no se asignan a lotes (R-INV-3): se supone que sale primero lo más antiguo, así
    el stock actual corresponde a las entradas más recientes.
    """
    remaining = quantity
    nearest: date | None = None
    for entry in sorted(entries, key=lambda e: (e.occurred_on, e.recorded_at), reverse=True):
        if remaining <= 0:
            break
        if entry.kind is not MovementKind.ENTRY:
            continue
        remaining -= entry.quantity
        if entry.expires_on is not None and (nearest is None or entry.expires_on < nearest):
            nearest = entry.expires_on
    return nearest


def is_expiring_soon(expiry: date | None, today: date) -> bool:
    """R-INV-4: vence en 15 días o menos, o ya venció."""
    return expiry is not None and expiry <= today + timedelta(days=EXPIRY_WARNING_DAYS)
