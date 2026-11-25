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
REFERENCE_MAX_LENGTH = 100
REASON_MAX_LENGTH = 500


class PaymentKind(StrEnum):
    ADVANCE = "ADVANCE"  # adelanto del contrato: primer pago del evento (HU42)
    INSTALLMENT = "INSTALLMENT"  # pago parcial posterior al adelanto (HU19)
    REFUND = "REFUND"  # devolución registrada al anular (R-CON-3)


# CA-19.5: solo un pago parcial se anula por aquí. El adelanto se anula con el contrato
# (R-CON-3) y una devolución no se anula.
VOIDABLE_KINDS = frozenset({PaymentKind.INSTALLMENT})


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


class LedgerRuleError(Exception):
    """Operación no permitida en el estado actual (responde 409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Payment:
    id: UUID
    number: str  # PAG-AAAA-NNNN (CA-20.1)
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
        number: str,
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
        cleaned = clean_reference(reference, "payment")
        return cls(
            id=uuid4(),
            number=number,
            contract_id=contract_id,
            kind=kind,
            amount_cents=amount_cents,
            method=method,
            reference=cleaned,
            paid_on=paid_on,
            recorded_by=recorded_by,
            recorded_at=now,
        )


@dataclass(frozen=True)
class PaymentVoid:
    """Anulación de un pago (CA-19.5, RN17): una fila aparte; el pago queda como estaba."""

    payment_id: UUID
    reason: str
    voided_by: UUID
    voided_at: datetime

    @classmethod
    def of(cls, payment: Payment, *, reason: str, voided_by: UUID, now: datetime) -> PaymentVoid:
        """Que el pago no tenga ya otra anulación lo revisa aplicación."""
        if payment.kind not in VOIDABLE_KINDS:
            raise LedgerRuleError(
                "payment.not_voidable",
                "Solo se anula un pago parcial. El adelanto se anula con el contrato.",
            )
        return cls(
            payment_id=payment.id,
            reason=check_reason(reason, "payment"),
            voided_by=voided_by,
            voided_at=now,
        )


def check_reason(reason: str, prefix: str) -> str:
    """Motivo obligatorio de una anulación (1–500 caracteres). Devuelve el motivo limpio."""
    cleaned = " ".join((reason or "").split())
    if not cleaned:
        raise LedgerValidationError(
            f"{prefix}.reason_required", "Indica el motivo de la anulación."
        )
    if len(cleaned) > REASON_MAX_LENGTH:
        raise LedgerValidationError(
            f"{prefix}.reason_too_long",
            f"El motivo no puede superar {REASON_MAX_LENGTH} caracteres.",
        )
    return cleaned


def clean_reference(reference: str | None, prefix: str) -> str | None:
    cleaned = " ".join((reference or "").split()) or None
    if cleaned and len(cleaned) > REFERENCE_MAX_LENGTH:
        raise LedgerValidationError(
            f"{prefix}.reference_too_long",
            f"La referencia no puede superar {REFERENCE_MAX_LENGTH} caracteres.",
        )
    return cleaned


def format_payment_number(year: int, number: int) -> str:
    """PAG-AAAA-NNNN; el correlativo se reinicia cada año, como COT, CON y EVT."""
    return f"PAG-{year}-{number:04d}"
