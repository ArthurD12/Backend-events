"""Flujo de caja entre dos fechas (HU22, CA-22.1, CA-22.2, CA-22.4).

Por fecha del pago o del movimiento, no de registro. Nada anulado entra (lo filtra `ledger`).
Ingresos = pagos de clientes netos de devoluciones + otros ingresos; egresos por categoría.
"""

from dataclasses import dataclass
from datetime import date

from local_eventos.modules.ledger.public_api import CashTotalsLookup, MonthlyCash, MovementCategory
from local_eventos.modules.reporting.application.errors import ReportRangeInvalidError

MAX_DAYS = 366
EXPENSE_CATEGORIES = (
    MovementCategory.SUPPLIES,
    MovementCategory.STAFF,
    MovementCategory.TRANSPORT,
    MovementCategory.OTHER_EXPENSE,
)


@dataclass(frozen=True)
class CashSummary:
    client_payments_cents: int  # netos de devoluciones
    refunds_cents: int
    other_income_cents: int
    expenses_by_category: dict[MovementCategory, int]

    @property
    def income_cents(self) -> int:
        return self.client_payments_cents + self.other_income_cents

    @property
    def expense_cents(self) -> int:
        return sum(self.expenses_by_category.values())

    @property
    def net_cents(self) -> int:
        return self.income_cents - self.expense_cents

    @classmethod
    def of(cls, months: list[MonthlyCash]) -> "CashSummary":
        return cls(
            client_payments_cents=sum(m.client_payments_cents - m.refunds_cents for m in months),
            refunds_cents=sum(m.refunds_cents for m in months),
            other_income_cents=sum(
                m.by_category.get(MovementCategory.OTHER_INCOME, 0) for m in months
            ),
            expenses_by_category={
                c: sum(m.by_category.get(c, 0) for m in months) for c in EXPENSE_CATEGORIES
            },
        )


@dataclass(frozen=True)
class CashFlowMonth:
    year: int
    month: int
    summary: CashSummary


@dataclass(frozen=True)
class CashFlow:
    date_from: date
    date_to: date
    summary: CashSummary
    months: list[CashFlowMonth]  # CA-22.2: un elemento por mes con movimiento


class GetCashFlow:
    def __init__(self, cash_totals: CashTotalsLookup) -> None:
        self._cash_totals = cash_totals

    async def __call__(self, date_from: date, date_to: date) -> CashFlow:
        if date_to < date_from or (date_to - date_from).days + 1 > MAX_DAYS:
            raise ReportRangeInvalidError(MAX_DAYS)
        months = await self._cash_totals(date_from, date_to)
        return CashFlow(
            date_from=date_from,
            date_to=date_to,
            summary=CashSummary.of(months),
            months=[CashFlowMonth(m.year, m.month, CashSummary.of([m])) for m in months],
        )
