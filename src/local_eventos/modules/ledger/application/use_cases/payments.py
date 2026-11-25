"""Casos de uso de pagos que otros módulos usan por `ledger.public_api`."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from local_eventos.modules.ledger.application.errors import (
    PaymentAlreadyVoidedError,
    PaymentNotFoundError,
)
from local_eventos.modules.ledger.application.ports.payment_repository import (
    PaymentEntry,
    PaymentRepository,
)
from local_eventos.modules.ledger.domain.payment import (
    Payment,
    PaymentKind,
    PaymentMethod,
    PaymentVoid,
    format_payment_number,
)


@dataclass(frozen=True)
class PaymentRequest:
    contract_id: UUID
    kind: PaymentKind
    amount_cents: int
    method: PaymentMethod
    reference: str | None
    paid_on: date
    recorded_by: UUID


class RecordPayment:
    def __init__(self, payments: PaymentRepository) -> None:
        self._payments = payments

    async def __call__(self, request: PaymentRequest, *, now: datetime, today: date) -> Payment:
        # Valida todo con un número provisional: si algo falla, no se gasta un correlativo.
        self._record(request, "", now=now, today=today)
        number = await self._payments.next_number(today.year)
        payment = self._record(
            request, format_payment_number(today.year, number), now=now, today=today
        )
        await self._payments.add(payment)
        return payment

    @staticmethod
    def _record(request: PaymentRequest, number: str, *, now: datetime, today: date) -> Payment:
        return Payment.record(
            number=number,
            contract_id=request.contract_id,
            kind=request.kind,
            amount_cents=request.amount_cents,
            method=request.method,
            reference=request.reference,
            paid_on=request.paid_on,
            recorded_by=request.recorded_by,
            now=now,
            today=today,
        )


class ContractPayments:
    def __init__(self, payments: PaymentRepository) -> None:
        self._payments = payments

    async def __call__(self, contract_id: UUID) -> list[Payment]:
        return await self._payments.list_for_contract(contract_id)


class ContractPaymentEntries:
    """Pagos del contrato con su anulación: con esto `commercial` calcula el saldo."""

    def __init__(self, payments: PaymentRepository) -> None:
        self._payments = payments

    async def __call__(self, contract_id: UUID) -> list[PaymentEntry]:
        return await self._payments.entries_for_contract(contract_id)


class FindPayment:
    def __init__(self, payments: PaymentRepository) -> None:
        self._payments = payments

    async def __call__(self, payment_id: UUID) -> PaymentEntry | None:
        return await self._payments.get(payment_id)


class VoidPayment:
    """Anula un pago parcial con motivo (CA-19.5, RN17): se inserta la anulación aparte."""

    def __init__(self, payments: PaymentRepository) -> None:
        self._payments = payments

    async def __call__(
        self, payment_id: UUID, *, reason: str, voided_by: UUID, now: datetime
    ) -> PaymentEntry:
        entry = await self._payments.get(payment_id)
        if entry is None:
            raise PaymentNotFoundError()
        if entry.void is not None:
            raise PaymentAlreadyVoidedError()
        void = PaymentVoid.of(entry.payment, reason=reason, voided_by=voided_by, now=now)
        await self._payments.add_void(void)
        return PaymentEntry(payment=entry.payment, void=void)
