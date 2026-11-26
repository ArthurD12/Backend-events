"""Reserva de un producto para un evento (HU25, R-REC-3).

Es un apartado sin movimiento de stock: baja lo disponible para otros eventos, no el stock.
Vence al cancelar o finalizar el evento. Python puro (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from local_eventos.modules.inventory.domain.errors import InventoryValidationError
from local_eventos.modules.inventory.domain.quantity import ZERO, to_quantity


class ReservationStatus(StrEnum):
    ACTIVE = "ACTIVE"  # vigente: aparta stock
    CONSUMED = "CONSUMED"  # se agotó al registrar salidas al evento
    RELEASED = "RELEASED"  # se liberó (a mano, o al cancelar o finalizar el evento)


@dataclass
class Reservation:
    id: UUID
    event_id: UUID
    product_id: UUID
    quantity: Decimal
    status: ReservationStatus
    created_by: UUID
    created_at: datetime
    closed_at: datetime | None = None

    @classmethod
    def open(
        cls, *, event_id: UUID, product_id: UUID, quantity: Decimal, by: UUID, now: datetime
    ) -> Reservation:
        return cls(
            id=uuid4(),
            event_id=event_id,
            product_id=product_id,
            quantity=check_reserved_quantity(quantity),
            status=ReservationStatus.ACTIVE,
            created_by=by,
            created_at=now,
        )

    def add(self, quantity: Decimal) -> None:
        self.quantity = self.quantity + check_reserved_quantity(quantity)

    def consume(self, quantity: Decimal, now: datetime) -> Decimal:
        """Descuenta de la reserva lo que sale al evento y devuelve cuánto consumió."""
        consumed = min(self.quantity, quantity)
        self.quantity = self.quantity - consumed
        if self.quantity <= ZERO:
            self.quantity = consumed  # la fila conserva lo último que apartaba (cantidad > 0)
            self.status = ReservationStatus.CONSUMED
            self.closed_at = now
        return consumed

    def release(self, now: datetime) -> None:
        self.status = ReservationStatus.RELEASED
        self.closed_at = now


def check_reserved_quantity(quantity: Decimal) -> Decimal:
    amount = to_quantity(quantity)
    if amount <= 0:
        raise InventoryValidationError("La cantidad a reservar debe ser mayor que cero.")
    return amount
