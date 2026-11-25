"""Materiales de un evento (HU26, CA-26.6): qué salió, qué volvió, qué se perdió y qué falta.

Python puro: no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from local_eventos.modules.inventory.domain.movement import Movement, MovementKind
from local_eventos.modules.inventory.domain.product import ProductKind
from local_eventos.modules.inventory.domain.quantity import ZERO


@dataclass(frozen=True)
class EventMaterials:
    """Totales de un producto en un evento."""

    product_id: UUID
    kind: ProductKind
    out: Decimal = ZERO
    returned: Decimal = ZERO
    wasted: Decimal = ZERO

    @property
    def at_event(self) -> Decimal:
        """Lo que salió y aún no volvió ni se dio por perdido: tope de una devolución o merma."""
        return max(self.out - self.returned - self.wasted, ZERO)

    @property
    def pending_return(self) -> Decimal:
        """Solo los reutilizables tienen que volver; los consumibles se gastan."""
        return self.at_event if self.kind is ProductKind.REUSABLE else ZERO

    @classmethod
    def from_movements(
        cls, product_id: UUID, kind: ProductKind, movements: list[Movement]
    ) -> EventMaterials:
        out = returned = wasted = ZERO
        for movement in movements:
            if movement.product_id != product_id:
                continue
            if movement.kind is MovementKind.EXIT:
                out += movement.quantity
            elif movement.kind is MovementKind.RETURN:
                returned += movement.quantity
            elif movement.kind is MovementKind.WASTE:
                wasted += movement.quantity
        return cls(product_id, kind, out, returned, wasted)
