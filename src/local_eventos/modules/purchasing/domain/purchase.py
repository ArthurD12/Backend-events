"""Compra a un proveedor (HU28, HU29): nace como solicitud, se ordena y se recibe o se cancela.

RN21: `REQUESTED → ORDERED → RECEIVED | CANCELLED`. Recibida o cancelada ya no cambia
(CA-29.3). La recepción es completa (R-COM-2): se confirma la cantidad real de cada línea.
Python puro: no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from uuid import UUID, uuid4

from local_eventos.modules.purchasing.domain.errors import (
    ExpenseAlreadyRegisteredError,
    ExpenseNotAvailableError,
    InvalidTransitionError,
    PurchasingValidationError,
)

CURRENCY = "PEN"
_STEP = Decimal("0.001")
_MAX_QUANTITY = Decimal("999999999.999")
LOT_MAX_LENGTH = 50
TEXT_MAX_LENGTH = 500
INVOICE_MAX_LENGTH = 50


class PurchaseStatus(StrEnum):
    REQUESTED = "REQUESTED"  # solicitada
    ORDERED = "ORDERED"  # ordenada al proveedor
    RECEIVED = "RECEIVED"  # recibida: ya entró al almacén
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class PurchaseLine:
    product_id: UUID
    quantity: Decimal  # pedida
    unit_cost_cents: int | None = None  # al ordenar
    received_quantity: Decimal | None = None  # al recibir
    lot: str | None = None
    expires_on: date | None = None

    @property
    def total_cents(self) -> int | None:
        if self.unit_cost_cents is None:
            return None
        quantity = self.quantity if self.received_quantity is None else self.received_quantity
        return int((quantity * self.unit_cost_cents).quantize(Decimal(1), ROUND_HALF_UP))


@dataclass(frozen=True)
class ReceivedLine:
    product_id: UUID
    quantity: Decimal
    lot: str | None = None
    expires_on: date | None = None


@dataclass(frozen=True)
class Stamp:
    """Quién y cuándo (RN03)."""

    by: UUID
    at: datetime


@dataclass
class Purchase:
    id: UUID
    code: str
    status: PurchaseStatus
    lines: tuple[PurchaseLine, ...]
    created: Stamp
    event_id: UUID | None = None
    notes: str | None = None
    supplier_id: UUID | None = None
    ordered: Stamp | None = None
    invoice_number: str | None = None
    received: Stamp | None = None
    cancelled: Stamp | None = None
    cancel_reason: str | None = None
    expense_movement_id: UUID | None = None  # egreso de ledger (R-COM-3), una sola vez

    @classmethod
    def request(
        cls,
        *,
        code: str,
        lines: list[tuple[UUID, Decimal]],
        created_by: UUID,
        now: datetime,
        event_id: UUID | None = None,
        notes: str | None = None,
    ) -> Purchase:
        """CA-28.1: solicitud con líneas (producto, cantidad), opcionalmente de un evento."""
        if not lines:
            raise PurchasingValidationError("Agrega al menos un producto.")
        ids = [product_id for product_id, _ in lines]
        if len(set(ids)) != len(ids):
            raise PurchasingValidationError("Un producto aparece dos veces en la compra.")
        cleaned = []
        for product_id, quantity in lines:
            amount = to_quantity(quantity)
            if amount <= 0:
                raise PurchasingValidationError("La cantidad pedida debe ser mayor que cero.")
            cleaned.append(PurchaseLine(product_id=product_id, quantity=amount))
        return cls(
            id=uuid4(),
            code=code,
            status=PurchaseStatus.REQUESTED,
            lines=tuple(cleaned),
            created=Stamp(created_by, now),
            event_id=event_id,
            notes=_clean_text(notes, "La nota", TEXT_MAX_LENGTH),
        )

    @property
    def total_cents(self) -> int | None:
        """CA-29.4: total calculado de las líneas (pedido al ordenar, real al recibir)."""
        totals = [line.total_cents for line in self.lines]
        return None if any(t is None for t in totals) else sum(t or 0 for t in totals)

    def order(
        self, *, supplier_id: UUID, unit_costs: dict[UUID, int], ordered_by: UUID, now: datetime
    ) -> None:
        """CA-29.1: elige proveedor y costo unitario de cada línea. Que esté activo lo ve app."""
        if self.status is not PurchaseStatus.REQUESTED:
            raise InvalidTransitionError("Solo se ordena una compra solicitada.")
        if set(unit_costs) != {line.product_id for line in self.lines}:
            raise PurchasingValidationError("Indica el costo unitario de cada línea.")
        for cost in unit_costs.values():
            if isinstance(cost, bool) or not isinstance(cost, int) or cost < 0:
                raise PurchasingValidationError("El costo unitario debe ser un entero ≥ 0.")
        self.lines = tuple(
            replace(line, unit_cost_cents=unit_costs[line.product_id]) for line in self.lines
        )
        self.supplier_id = supplier_id
        self.ordered = Stamp(ordered_by, now)
        self.status = PurchaseStatus.ORDERED

    def receive(
        self,
        *,
        lines: list[ReceivedLine],
        received_by: UUID,
        now: datetime,
        invoice_number: str | None = None,
    ) -> None:
        """CA-29.2 y CA-29.3: una sola vez; cantidades reales, lote y vencimiento por línea."""
        if self.status is not PurchaseStatus.ORDERED:
            raise InvalidTransitionError("Solo se recibe una compra ordenada, y una sola vez.")
        by_product = {line.product_id: line for line in lines}
        if len(by_product) != len(lines) or set(by_product) != {
            line.product_id for line in self.lines
        }:
            raise PurchasingValidationError("Confirma la cantidad recibida de cada línea.")
        updated = []
        for line in self.lines:
            got = by_product[line.product_id]
            amount = to_quantity(got.quantity)
            if amount < 0:
                raise PurchasingValidationError("La cantidad recibida no puede ser negativa.")
            updated.append(
                replace(
                    line,
                    received_quantity=amount,
                    lot=_clean_text(got.lot, "El lote", LOT_MAX_LENGTH),
                    expires_on=got.expires_on,
                )
            )
        if all(line.received_quantity == 0 for line in updated):
            raise PurchasingValidationError("No llegó nada: cancela la compra en vez de recibirla.")
        self.lines = tuple(updated)
        self.invoice_number = _clean_text(invoice_number, "El comprobante", INVOICE_MAX_LENGTH)
        self.received = Stamp(received_by, now)
        self.status = PurchaseStatus.RECEIVED

    def expense_amount(self) -> int:
        """CA-30.3: monto del egreso (total real de la compra recibida), una sola vez."""
        if self.status is not PurchaseStatus.RECEIVED:
            raise ExpenseNotAvailableError("Solo una compra recibida se registra como egreso.")
        if self.expense_movement_id is not None:
            raise ExpenseAlreadyRegisteredError()
        total = self.total_cents
        if not total:
            raise ExpenseNotAvailableError("La compra no tiene un total mayor que cero.")
        return total

    def mark_expensed(self, movement_id: UUID) -> None:
        self.expense_movement_id = movement_id

    def cancel(self, *, reason: str, cancelled_by: UUID, now: datetime) -> None:
        if self.status not in (PurchaseStatus.REQUESTED, PurchaseStatus.ORDERED):
            raise InvalidTransitionError("Una compra recibida o cancelada no cambia.")
        cleaned = _clean_text(reason, "El motivo", TEXT_MAX_LENGTH)
        if cleaned is None:
            raise PurchasingValidationError("Para cancelar la compra, indica el motivo.")
        self.cancel_reason = cleaned
        self.cancelled = Stamp(cancelled_by, now)
        self.status = PurchaseStatus.CANCELLED


def to_quantity(value: Decimal | int | str) -> Decimal:
    """Hasta 3 decimales (R-INV-1); más decimales es un error, no se redondea."""
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise PurchasingValidationError("La cantidad no es un número válido.") from error
    if not number.is_finite() or number != number.quantize(_STEP, rounding="ROUND_DOWN"):
        raise PurchasingValidationError("La cantidad admite hasta 3 decimales.")
    if abs(number) > _MAX_QUANTITY:
        raise PurchasingValidationError("La cantidad es demasiado grande.")
    return number.quantize(_STEP) + Decimal("0.000")


def format_purchase_code(year: int, number: int) -> str:
    """COM-AAAA-NNNN; el correlativo se reinicia cada año, como COT, CON y EVT."""
    return f"COM-{year}-{number:04d}"


def _clean_text(value: str | None, label: str, limit: int) -> str | None:
    cleaned = " ".join((value or "").split()) or None
    if cleaned and len(cleaned) > limit:
        raise PurchasingValidationError(f"{label} no puede superar {limit} caracteres.")
    return cleaned
