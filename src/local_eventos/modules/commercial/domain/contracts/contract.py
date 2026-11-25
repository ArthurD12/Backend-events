"""Contrato de Darze (HU41–HU42): formaliza una cotización aceptada.

`pendiente de firma → firmado | anulado`. Copia del cliente, la fecha del evento y el total de la
cotización aceptada; el detalle de servicios es el de esa cotización, que ya no puede cambiar.
Python puro: no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from local_eventos.modules.commercial.domain.quotes.quote import Quote, QuoteStatus

DEFAULT_ADVANCE_PERCENT = 50  # DOMAIN.md §4, regla 3
BALANCE_DAYS_BEFORE_EVENT = 7  # DOMAIN.md §4, regla 3
_SIGNER_MAX_LENGTH = 120
_TEXT_MAX_LENGTH = 500


class ContractStatus(StrEnum):
    PENDING_SIGNATURE = "PENDING_SIGNATURE"
    SIGNED = "SIGNED"
    CANCELLED = "CANCELLED"


class ContractValidationError(ValueError):
    """Dato inválido (responde 422)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ContractRuleError(Exception):
    """Operación no permitida en el estado actual (responde 409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Signature:
    signed_on: date
    signer_name: str
    advance_payment_id: UUID
    recorded_by: UUID
    recorded_at: datetime


@dataclass(frozen=True)
class Cancellation:
    reason: str
    refund_cents: int | None
    refund_payment_id: UUID | None
    note: str | None
    cancelled_by: UUID
    cancelled_at: datetime


@dataclass
class Contract:
    id: UUID
    code: str
    quote_id: UUID
    client_id: UUID
    event_date: date
    total_cents: int
    advance_cents: int
    balance_due_date: date
    status: ContractStatus
    created_by: UUID
    created_at: datetime
    signature: Signature | None = None
    cancellation: Cancellation | None = None

    @classmethod
    def generate(
        cls,
        *,
        code: str,
        quote: Quote,
        today: date,
        created_by: UUID,
        now: datetime,
        advance_cents: int | None = None,
    ) -> Contract:
        """CA-41.1 a CA-41.5. Que la cotización no tenga otro contrato lo revisa aplicación."""
        if quote.effective_status(today) is not QuoteStatus.ACCEPTED:
            raise ContractRuleError(
                "contract.quote_not_accepted",
                "Solo se genera un contrato de una cotización aceptada.",
            )
        total = quote.total_cents
        advance = default_advance(total) if advance_cents is None else advance_cents
        if isinstance(advance, bool) or not isinstance(advance, int) or not 0 < advance <= total:
            raise ContractValidationError(
                "contract.advance_invalid",
                "El adelanto debe ser mayor que cero y no superar el total.",
            )
        event_date = quote.details.event_date
        return cls(
            id=uuid4(),
            code=code,
            quote_id=quote.id,
            client_id=quote.client_id,
            event_date=event_date,
            total_cents=total,
            advance_cents=advance,
            balance_due_date=event_date - timedelta(days=BALANCE_DAYS_BEFORE_EVENT),
            status=ContractStatus.PENDING_SIGNATURE,
            created_by=created_by,
            created_at=now,
        )

    @property
    def balance_cents(self) -> int:
        """Saldo pactado: lo que falta pagar después del adelanto. El saldo real, con los pagos
        registrados, es `ContractBalance`."""
        return self.total_cents - self.advance_cents

    @property
    def can_become_event(self) -> bool:
        """CA-42.3: solo un contrato firmado y con adelanto pagado (lo garantiza `sign`)."""
        return self.status is ContractStatus.SIGNED and self.signature is not None

    def ensure_pending(self) -> None:
        if self.status is not ContractStatus.PENDING_SIGNATURE:
            raise ContractRuleError(
                "contract.not_pending",
                "Solo se registra la firma de un contrato pendiente de firma.",
            )

    def sign(
        self,
        *,
        signed_on: date,
        signer_name: str,
        advance_payment_id: UUID,
        recorded_by: UUID,
        now: datetime,
        today: date,
    ) -> None:
        """CA-42.1 y R-CON-1: firma y adelanto en un solo paso."""
        self.ensure_pending()
        checked_on, checked_name = check_signature(signed_on, signer_name, today)
        self.signature = Signature(
            signed_on=checked_on,
            signer_name=checked_name,
            advance_payment_id=advance_payment_id,
            recorded_by=recorded_by,
            recorded_at=now,
        )
        self.status = ContractStatus.SIGNED

    def check_cancellation(self, reason: str, refund_cents: int | None) -> str:
        """Valida antes de registrar nada en pagos. Devuelve el motivo limpio."""
        if self.status is ContractStatus.CANCELLED:
            raise ContractRuleError("contract.already_cancelled", "El contrato ya está anulado.")
        cleaned = _clean(reason)
        if not cleaned:
            raise ContractValidationError(
                "contract.reason_required", "Para anular el contrato, indica el motivo."
            )
        if len(cleaned) > _TEXT_MAX_LENGTH:
            raise ContractValidationError(
                "contract.reason_too_long",
                f"El motivo no puede superar {_TEXT_MAX_LENGTH} caracteres.",
            )
        if refund_cents is not None:
            paid = self.advance_cents if self.status is ContractStatus.SIGNED else 0
            if isinstance(refund_cents, bool) or not 0 < refund_cents <= paid:
                raise ContractValidationError(
                    "contract.refund_invalid",
                    "La devolución debe ser mayor que cero y no superar el adelanto pagado.",
                )
        return cleaned

    def cancel(
        self,
        *,
        reason: str,
        refund_cents: int | None,
        refund_payment_id: UUID | None,
        note: str | None,
        cancelled_by: UUID,
        now: datetime,
    ) -> None:
        """CA-42.4 y R-CON-3: con motivo; la devolución solo se registra, no se calcula."""
        cleaned = self.check_cancellation(reason, refund_cents)
        self.cancellation = Cancellation(
            reason=cleaned,
            refund_cents=refund_cents,
            refund_payment_id=refund_payment_id,
            note=_clean(note) or None,
            cancelled_by=cancelled_by,
            cancelled_at=now,
        )
        self.status = ContractStatus.CANCELLED


@dataclass(frozen=True)
class ContractBalance:
    """Cuenta del contrato (HU19, RN15). Solo cuentan los pagos vigentes (CA-19.3).

    - Pendiente de firma: saldo = total − adelanto pactado (aún no hay pagos; el adelanto se
      paga al firmar, R-CON-1).
    - Firmado: saldo = total − pagos + devoluciones.
    - Anulado: no hay saldo por cobrar (0). Lo pagado y lo devuelto se siguen mostrando.
    """

    status: ContractStatus
    total_cents: int
    paid_cents: int
    refunded_cents: int
    balance_cents: int
    due_date: date

    @classmethod
    def of(cls, contract: Contract, *, paid_cents: int, refunded_cents: int) -> ContractBalance:
        if contract.status is ContractStatus.PENDING_SIGNATURE:
            balance = contract.balance_cents
        elif contract.status is ContractStatus.CANCELLED:
            balance = 0  # un contrato anulado no tiene nada por cobrar
        else:
            balance = contract.total_cents - paid_cents + refunded_cents
        return cls(
            status=contract.status,
            total_cents=contract.total_cents,
            paid_cents=paid_cents,
            refunded_cents=refunded_cents,
            balance_cents=balance,
            due_date=contract.balance_due_date,
        )

    def is_overdue(self, today: date) -> bool:
        """R-PAG-2: solo un aviso. Se puede pagar después de la fecha límite."""
        return (
            self.status is ContractStatus.SIGNED
            and self.balance_cents > 0
            and today > self.due_date
        )

    def ensure_can_pay(self, amount_cents: int) -> None:
        """CA-19.1, CA-19.6: solo en un contrato firmado. RN14: sin superar el saldo."""
        if self.status is not ContractStatus.SIGNED:
            raise ContractRuleError(
                "contract.not_signed", "Solo se registran pagos en un contrato firmado."
            )
        if isinstance(amount_cents, int) and amount_cents > self.balance_cents:
            raise ContractValidationError(
                "payment.exceeds_balance",
                f"El pago supera el saldo pendiente de S/ {self.balance_cents / 100:,.2f}.",
            )


def default_advance(total_cents: int) -> int:
    """50 % del total, redondeado al céntimo (medio céntimo hacia arriba)."""
    return (total_cents * DEFAULT_ADVANCE_PERCENT + 50) // 100


def check_signature(signed_on: date, signer_name: str, today: date) -> tuple[date, str]:
    name = _clean(signer_name)
    if not name:
        raise ContractValidationError("contract.signer_required", "Indica quién firmó el contrato.")
    if len(name) > _SIGNER_MAX_LENGTH:
        raise ContractValidationError(
            "contract.signer_too_long",
            f"El nombre del firmante no puede superar {_SIGNER_MAX_LENGTH} caracteres.",
        )
    if signed_on > today:
        raise ContractValidationError(
            "contract.signed_on_future", "La fecha de firma no puede ser posterior a hoy."
        )
    return signed_on, name


def format_contract_code(year: int, number: int) -> str:
    """CON-AAAA-NNNN; el correlativo se reinicia cada año (DOMAIN.md §4, regla 8)."""
    return f"CON-{year}-{number:04d}"


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())
