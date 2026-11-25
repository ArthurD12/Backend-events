"""Sumas de caja para `reporting` (HU22). Nada anulado entra en los cálculos (CA-22.4)."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from local_eventos.modules.ledger.application.ports.movement_repository import MovementRepository
from local_eventos.modules.ledger.application.ports.payment_repository import PaymentRepository
from local_eventos.modules.ledger.domain.movement import MovementCategory
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
