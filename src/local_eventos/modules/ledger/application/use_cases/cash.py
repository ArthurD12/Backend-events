"""Sumas de caja para `reporting` (HU22). Nada anulado entra en los cálculos (CA-22.4)."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID

from local_eventos.modules.ledger.application.ports.movement_repository import MovementRepository
from local_eventos.modules.ledger.application.ports.payment_repository import (
    ContractPaidTotals,
    PaymentRepository,
)
from local_eventos.modules.ledger.domain.movement import MovementCategory, MovementType
from local_eventos.modules.ledger.domain.payment import PaymentKind


@dataclass(frozen=True)
class MonthlyCash:
    """Lo que entró y salió en un mes. Pagos de clientes y devoluciones por separado."""

    year: int
    month: int
    client_payments_cents: int
    refunds_cents: int
    by_category: dict[MovementCategory, int]


class CashTotals:
    def __init__(self, payments: PaymentRepository, movements: MovementRepository) -> None:
        self._payments = payments
        self._movements = movements

    async def __call__(self, date_from: date, date_to: date) -> list[MonthlyCash]:
        """Un elemento por mes con movimiento, del más antiguo al más reciente."""
        months: dict[tuple[int, int], dict[str, int]] = {}
        for p in await self._payments.monthly_totals(date_from, date_to):
            key = "refunds" if p.kind is PaymentKind.REFUND else "client"
            bucket = months.setdefault((p.year, p.month), {})
            bucket[key] = bucket.get(key, 0) + p.amount_cents
        for m in await self._movements.monthly_totals(date_from, date_to):
            bucket = months.setdefault((m.year, m.month), {})
            bucket[m.category.value] = bucket.get(m.category.value, 0) + m.amount_cents
        return [
            MonthlyCash(
                year=year,
                month=month,
                client_payments_cents=values.get("client", 0),
                refunds_cents=values.get("refunds", 0),
                by_category={c: values[c.value] for c in MovementCategory if c.value in values},
            )
            for (year, month), values in sorted(months.items())
        ]


class EventCash:
    def __init__(self, movements: MovementRepository) -> None:
        self._movements = movements

    async def __call__(self, event_id: UUID) -> dict[MovementCategory, int]:
        """Ingresos y egresos vigentes asociados al evento, por categoría."""
        return await self._movements.event_totals(event_id)


class ContractPaidTotalsQuery:
    """Pagado y devuelto de varios contratos en una consulta (reportes y panel, HU31–HU34)."""

    def __init__(self, payments: PaymentRepository) -> None:
        self._payments = payments

    async def __call__(self, contract_ids: list[UUID]) -> dict[UUID, ContractPaidTotals]:
        """Los contratos sin pagos vigentes vuelven con ceros."""
        totals = await self._payments.paid_totals(list(dict.fromkeys(contract_ids)))
        return {c: totals.get(c, ContractPaidTotals()) for c in contract_ids}


class CashEntryKind(StrEnum):
    CLIENT_PAYMENT = "CLIENT_PAYMENT"  # adelanto o pago parcial de un contrato
    REFUND = "REFUND"  # devolución al cliente
    INCOME = "INCOME"  # otro ingreso
    EXPENSE = "EXPENSE"  # egreso


@dataclass(frozen=True)
class CashEntry:
    """Una línea del reporte de caja (CA-32.2): pago de cliente o movimiento, con su anulación.

    `concept` es el concepto del movimiento o el número del pago (PAG-AAAA-NNNN).
    """

    occurred_on: date
    kind: CashEntryKind
    category: MovementCategory | None
    payment_kind: PaymentKind | None
    concept: str
    amount_cents: int
    contract_id: UUID | None
    event_id: UUID | None
    voided: bool


class CashEntries:
    def __init__(self, payments: PaymentRepository, movements: MovementRepository) -> None:
        self._payments = payments
        self._movements = movements

    async def __call__(self, date_from: date, date_to: date) -> list[CashEntry]:
        """Pagos y movimientos del rango, anulados incluidos (marcados), por fecha."""
        entries = [
            CashEntry(
                occurred_on=e.payment.paid_on,
                kind=CashEntryKind.REFUND
                if e.payment.kind is PaymentKind.REFUND
                else CashEntryKind.CLIENT_PAYMENT,
                category=None,
                payment_kind=e.payment.kind,
                concept=e.payment.number,
                amount_cents=e.payment.amount_cents,
                contract_id=e.payment.contract_id,
                event_id=None,
                voided=e.is_voided,
            )
            for e in await self._payments.entries_between(date_from, date_to)
        ]
        entries += [
            CashEntry(
                occurred_on=e.movement.occurred_on,
                kind=CashEntryKind.INCOME
                if e.movement.type is MovementType.INCOME
                else CashEntryKind.EXPENSE,
                category=e.movement.category,
                payment_kind=None,
                concept=e.movement.concept,
                amount_cents=e.movement.amount_cents,
                contract_id=None,
                event_id=e.movement.event_id,
                voided=e.void is not None,
            )
            for e in await self._movements.entries_between(date_from, date_to)
        ]
        return sorted(entries, key=lambda e: e.occurred_on)  # estable: pagos antes, mismo día
