"""Superficie pública del módulo ledger: única vía de uso por otros módulos.

`commercial` registra aquí el adelanto y las devoluciones del contrato, dentro de la misma
transacción de la petición: si algo falla, no queda ni el contrato firmado ni el pago.
"""

from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.ledger import composition
from local_eventos.modules.ledger.application.use_cases.payments import (
    ContractPayments,
    PaymentRequest,
    RecordPayment,
)
from local_eventos.modules.ledger.domain.payment import (
    LedgerValidationError,
    Payment,
    PaymentKind,
    PaymentMethod,
)


class PaymentRecorder(Protocol):
    async def __call__(self, request: PaymentRequest, *, now: datetime, today: date) -> Payment: ...


class PaymentsLookup(Protocol):
    async def __call__(self, contract_id: UUID) -> list[Payment]: ...


def payment_recorder(session: AsyncSession) -> PaymentRecorder:
    return RecordPayment(composition.payment_repository(session))


def payments_lookup(session: AsyncSession) -> PaymentsLookup:
    return ContractPayments(composition.payment_repository(session))


__all__ = [
    "LedgerValidationError",
    "Payment",
    "PaymentKind",
    "PaymentMethod",
    "PaymentRecorder",
    "PaymentRequest",
    "PaymentsLookup",
    "payments_lookup",
    "payment_recorder",
]
