"""Superficie pública del módulo ledger: única vía de uso por otros módulos.

`commercial` registra y anula aquí los pagos del contrato (adelanto, pagos parciales y
devoluciones) dentro de la misma transacción de la petición: si algo falla, no queda nada a
medias. `ledger` no conoce a `commercial` (sin ciclo de imports). `reporting` lee las sumas.
"""

from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.ledger import composition
from local_eventos.modules.ledger.application.errors import PaymentNotFoundError
from local_eventos.modules.ledger.application.ports.movement_repository import MovementEntry
from local_eventos.modules.ledger.application.ports.payment_repository import (
    ContractPaidTotals,
    PaymentEntry,
)
from local_eventos.modules.ledger.application.use_cases.cash import (
    CashEntries,
    CashEntry,
    CashEntryKind,
    CashTotals,
    ContractPaidTotalsQuery,
    EventCash,
    MonthlyCash,
)
from local_eventos.modules.ledger.application.use_cases.movements import (
    MovementRequest,
    RecordMovement,
)
from local_eventos.modules.ledger.application.use_cases.payments import (
    ContractPaymentEntries,
    ContractPayments,
    FindPayment,
    PaymentRequest,
    RecordPayment,
    VoidPayment,
)
from local_eventos.modules.ledger.domain.movement import MovementCategory, MovementType
from local_eventos.modules.ledger.domain.payment import (
    LedgerValidationError,
    Payment,
    PaymentKind,
    PaymentMethod,
    PaymentVoid,
)


class PaymentRecorder(Protocol):
    async def __call__(self, request: PaymentRequest, *, now: datetime, today: date) -> Payment: ...


class MovementRecorder(Protocol):
    """Registra un ingreso o egreso de caja (HU21), p. ej. el egreso de una compra recibida."""

    async def __call__(self, request: MovementRequest) -> MovementEntry: ...


class PaymentsLookup(Protocol):
    async def __call__(self, contract_id: UUID) -> list[Payment]: ...


class PaymentEntriesLookup(Protocol):
    """Pagos del contrato con su anulación, del más antiguo al más reciente."""

    async def __call__(self, contract_id: UUID) -> list[PaymentEntry]: ...


class PaymentFinder(Protocol):
    async def __call__(self, payment_id: UUID) -> PaymentEntry | None: ...


class PaymentVoider(Protocol):
    """Anula un pago parcial. Errores: `payment.not_found`, `payment.not_voidable`,
    `payment.already_voided`, `payment.reason_required`."""

    async def __call__(
        self, payment_id: UUID, *, reason: str, voided_by: UUID, now: datetime
    ) -> PaymentEntry: ...


class CashTotalsLookup(Protocol):
    """Pagos y movimientos vigentes del rango, por mes (HU22)."""

    async def __call__(self, date_from: date, date_to: date) -> list[MonthlyCash]: ...


class EventCashLookup(Protocol):
    """Ingresos y egresos vigentes asociados a un evento, por categoría (HU22)."""

    async def __call__(self, event_id: UUID) -> dict[MovementCategory, int]: ...


class ContractPaidTotalsLookup(Protocol):
    """Pagado y devuelto vigentes de varios contratos (reportes y panel, HU31–HU34)."""

    async def __call__(self, contract_ids: list[UUID]) -> dict[UUID, ContractPaidTotals]: ...


class CashEntriesLookup(Protocol):
    """Pagos y movimientos del rango, anulados incluidos y marcados (reporte de caja, CA-32.2)."""

    async def __call__(self, date_from: date, date_to: date) -> list[CashEntry]: ...


def payment_recorder(session: AsyncSession) -> PaymentRecorder:
    return RecordPayment(composition.payment_repository(session))


def movement_recorder(session: AsyncSession) -> MovementRecorder:
    return RecordMovement(composition.movement_repository(session), composition.clock())


def payments_lookup(session: AsyncSession) -> PaymentsLookup:
    return ContractPayments(composition.payment_repository(session))


def payment_entries(session: AsyncSession) -> PaymentEntriesLookup:
    return ContractPaymentEntries(composition.payment_repository(session))


def payment_finder(session: AsyncSession) -> PaymentFinder:
    return FindPayment(composition.payment_repository(session))


def payment_voider(session: AsyncSession) -> PaymentVoider:
    return VoidPayment(composition.payment_repository(session))


def cash_totals(session: AsyncSession) -> CashTotalsLookup:
    return CashTotals(
        composition.payment_repository(session), composition.movement_repository(session)
    )


def event_cash(session: AsyncSession) -> EventCashLookup:
    return EventCash(composition.movement_repository(session))


def contract_paid_totals(session: AsyncSession) -> ContractPaidTotalsLookup:
    """Consulta de solo lectura para `commercial` (saldo de varios contratos a la vez)."""
    return ContractPaidTotalsQuery(composition.payment_repository(session))


def cash_entries(session: AsyncSession) -> CashEntriesLookup:
    """Consulta de solo lectura para el reporte de caja (`reporting`)."""
    return CashEntries(
        composition.payment_repository(session), composition.movement_repository(session)
    )


__all__ = [
    "CashEntriesLookup",
    "CashEntry",
    "CashEntryKind",
    "CashTotalsLookup",
    "ContractPaidTotals",
    "ContractPaidTotalsLookup",
    "EventCashLookup",
    "LedgerValidationError",
    "MonthlyCash",
    "MovementEntry",
    "MovementRecorder",
    "MovementRequest",
    "MovementType",
    "MovementCategory",
    "Payment",
    "PaymentEntriesLookup",
    "PaymentEntry",
    "PaymentFinder",
    "PaymentKind",
    "PaymentMethod",
    "PaymentNotFoundError",
    "PaymentRecorder",
    "PaymentRequest",
    "PaymentVoid",
    "PaymentVoider",
    "PaymentsLookup",
    "cash_entries",
    "cash_totals",
    "movement_recorder",
    "contract_paid_totals",
    "event_cash",
    "payment_entries",
    "payment_finder",
    "payment_recorder",
    "payment_voider",
    "payments_lookup",
]
