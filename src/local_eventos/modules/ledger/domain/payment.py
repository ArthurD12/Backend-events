"""Pago registrado de Darze (DOMAIN.md §6). Inmutable: nunca se edita ni se borra.

Darze no usa pasarela: el pago se hizo fuera del sistema (efectivo, transferencia…) y aquí solo
se **registra**. Una devolución es otro movimiento, no un cambio del pago (AGENTS.md, regla 5).
Python puro: no importa FastAPI, SQLAlchemy ni Pydantic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

CURRENCY = "PEN"
_REFERENCE_MAX_LENGTH = 100


class PaymentKind(StrEnum):
    ADVANCE = "ADVANCE"  # adelanto del contrato: primer pago del evento (HU42)
    REFUND = "REFUND"  # devolución registrada al anular (R-CON-3)


class PaymentMethod(StrEnum):
    CASH = "CASH"
    TRANSFER = "TRANSFER"
    CARD = "CARD"
    YAPE_PLIN = "YAPE_PLIN"


class LedgerValidationError(ValueError):
    """Dato de pago inválido (responde 422). `code` es estable para el frontend."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Payment:
    id: UUID
    contract_id: UUID
    kind: PaymentKind
    amount_cents: int
    method: PaymentMethod
    reference: str | None
    paid_on: date
    recorded_by: UUID
    recorded_at: datetime

    @classmethod
    def record(
        cls,
        *,
        contract_id: UUID,
        kind: PaymentKind,
        amount_cents: int,
        method: PaymentMethod,
        reference: str | None,
        paid_on: date,
        recorded_by: UUID,
        now: datetime,
        today: date,
    ) -> Payment:
        if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents <= 0:
            raise LedgerValidationError(
                "payment.amount_invalid", "El monto del pago debe ser mayor que cero."
            )
        if paid_on > today:
            raise LedgerValidationError(
                "payment.date_in_future", "La fecha del pago no puede ser posterior a hoy."
            )
        cleaned = " ".join((reference or "").split()) or None
        if cleaned and len(cleaned) > _REFERENCE_MAX_LENGTH:
            raise LedgerValidationError(
                "payment.reference_too_long",
                f"La referencia no puede superar {_REFERENCE_MAX_LENGTH} caracteres.",
            )
        return cls(
            id=uuid4(),
            contract_id=contract_id,
            kind=kind,
            amount_cents=amount_cents,
            method=method,
            reference=cleaned,
            paid_on=paid_on,
            recorded_by=recorded_by,
            recorded_at=now,
        )
