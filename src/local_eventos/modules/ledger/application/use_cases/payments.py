"""Casos de uso de pagos que otros módulos usan por `ledger.public_api`."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from local_eventos.modules.ledger.application.ports.payment_repository import PaymentRepository
from local_eventos.modules.ledger.domain.payment import Payment, PaymentKind, PaymentMethod


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
        payment = Payment.record(
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
        await self._payments.add(payment)
        return payment


class ContractPayments:
    def __init__(self, payments: PaymentRepository) -> None:
        self._payments = payments

    async def __call__(self, contract_id: UUID) -> list[Payment]:
        return await self._payments.list_for_contract(contract_id)
