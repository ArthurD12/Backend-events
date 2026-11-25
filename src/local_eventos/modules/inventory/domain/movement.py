"""Movimiento de almacén (HU23, HU26): entrada, salida, devolución, merma o ajuste.

Es inmutable: no se edita ni se borra (R-INV-5, AGENTS.md regla 5). Un error se corrige con un
ajuste. `quantity` es positiva en todos los tipos menos en el ajuste, que lleva signo.
Python puro: no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from local_eventos.modules.inventory.domain.errors import InventoryValidationError
from local_eventos.modules.inventory.domain.quantity import ZERO, to_quantity

LOT_MAX_LENGTH = 50
TEXT_MAX_LENGTH = 500


class MovementKind(StrEnum):
    ENTRY = "ENTRY"  # entra al almacén (compra o ingreso manual), con costo
    EXIT = "EXIT"  # sale para un evento
    RETURN = "RETURN"  # vuelve de un evento lo que no se usó, o la vajilla
    WASTE = "WASTE"  # merma: se perdió o se dañó (en almacén o en un evento)
    ADJUSTMENT = "ADJUSTMENT"  # corrección del conteo, positiva o negativa


@dataclass(frozen=True)
class Movement:
    id: UUID
    product_id: UUID
    kind: MovementKind
    quantity: Decimal
    occurred_on: date
    recorded_by: UUID
    recorded_at: datetime
    event_id: UUID | None = None
    unit_cost_cents: int | None = None
    supplier_id: UUID | None = None
    lot: str | None = None
    expires_on: date | None = None
    reason: str | None = None
    purchase_id: UUID | None = None

    @property
    def stock_delta(self) -> Decimal:
        """Cuánto cambia el stock del almacén.

        Una merma de evento no cambia el stock: lo perdido ya había salido con la salida; solo
        reduce lo que falta devolver (decisión del equipo, 017).
        """
        if self.kind in (MovementKind.ENTRY, MovementKind.RETURN, MovementKind.ADJUSTMENT):
            return self.quantity
        if self.kind is MovementKind.WASTE and self.event_id is not None:
            return ZERO
        return -self.quantity

    @classmethod
    def record(
        cls,
        *,
        kind: MovementKind,
        product_id: UUID,
        quantity: Decimal,
        recorded_by: UUID,
        now: datetime,
        today: date,
        occurred_on: date | None = None,
        event_id: UUID | None = None,
        unit_cost_cents: int | None = None,
        supplier_id: UUID | None = None,
        lot: str | None = None,
        expires_on: date | None = None,
        reason: str | None = None,
        purchase_id: UUID | None = None,
    ) -> Movement:
        amount = to_quantity(quantity)
        if kind is MovementKind.ADJUSTMENT:
            if amount == 0:
                raise InventoryValidationError("El ajuste no puede ser cero.")
        elif amount <= 0:
            raise InventoryValidationError("La cantidad debe ser mayor que cero.")
        day = occurred_on or today
        if day > today:
            raise InventoryValidationError("La fecha no puede ser posterior a hoy.")
        if kind in (MovementKind.EXIT, MovementKind.RETURN) and event_id is None:
            raise InventoryValidationError("Indica el evento.")
        if kind in (MovementKind.ENTRY, MovementKind.ADJUSTMENT) and event_id is not None:
            raise InventoryValidationError("Una entrada o un ajuste no se asocia a un evento.")
        is_entry = kind is MovementKind.ENTRY
        if is_entry:
            if isinstance(unit_cost_cents, bool) or not isinstance(unit_cost_cents, int):
                raise InventoryValidationError("Indica el costo unitario en céntimos.")
            if unit_cost_cents < 0:
                raise InventoryValidationError("El costo unitario no puede ser negativo.")
        elif any(
            value is not None for value in (unit_cost_cents, supplier_id, lot, expires_on)
        ) or (purchase_id is not None):
            raise InventoryValidationError(
                "Costo, proveedor, lote y vencimiento solo van en una entrada."
            )
        cleaned_reason = _clean_text(reason, "El motivo")
        if kind in (MovementKind.WASTE, MovementKind.ADJUSTMENT) and cleaned_reason is None:
            raise InventoryValidationError("Indica el motivo.")
        return cls(
            id=uuid4(),
            product_id=product_id,
            kind=kind,
            quantity=amount,
            occurred_on=day,
            recorded_by=recorded_by,
            recorded_at=now,
            event_id=event_id,
            unit_cost_cents=unit_cost_cents,
            supplier_id=supplier_id,
            lot=_clean_lot(lot),
            expires_on=expires_on,
            reason=cleaned_reason,
            purchase_id=purchase_id,
        )


def _clean_text(value: str | None, label: str) -> str | None:
    cleaned = " ".join((value or "").split()) or None
    if cleaned and len(cleaned) > TEXT_MAX_LENGTH:
        raise InventoryValidationError(f"{label} no puede superar {TEXT_MAX_LENGTH} caracteres.")
    return cleaned


def _clean_lot(lot: str | None) -> str | None:
    cleaned = " ".join((lot or "").split()) or None
    if cleaned and len(cleaned) > LOT_MAX_LENGTH:
        raise InventoryValidationError(f"El lote no puede superar {LOT_MAX_LENGTH} caracteres.")
    return cleaned
