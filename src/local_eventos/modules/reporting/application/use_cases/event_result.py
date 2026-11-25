"""Resultado económico de un evento (HU22, CA-22.3, CA-22.4).

Cobrado al cliente (neto de devoluciones) − egresos asociados al evento. También el total
contratado y el saldo por cobrar. Nada anulado entra en los cálculos.
"""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.commercial.public_api import EventFinance, EventFinanceLookup
from local_eventos.modules.ledger.public_api import EventCashLookup, MovementCategory
from local_eventos.modules.reporting.application.errors import ReportEventNotFoundError
from local_eventos.modules.reporting.application.use_cases.cash_flow import EXPENSE_CATEGORIES


@dataclass(frozen=True)
class EventResult:
    finance: EventFinance
    expenses_by_category: dict[MovementCategory, int]

    @property
    def collected_cents(self) -> int:
        return self.finance.paid_cents - self.finance.refunded_cents

    @property
    def expense_cents(self) -> int:
        return sum(self.expenses_by_category.values())

    @property
    def result_cents(self) -> int:
        return self.collected_cents - self.expense_cents


class GetEventResult:
    def __init__(self, finance: EventFinanceLookup, event_cash: EventCashLookup) -> None:
        self._finance = finance
        self._event_cash = event_cash

    async def __call__(self, event_id: UUID) -> EventResult:
        finance = await self._finance(event_id)
        if finance is None:
            raise ReportEventNotFoundError()
        by_category = await self._event_cash(event_id)
        return EventResult(
            finance=finance,
            expenses_by_category={c: by_category.get(c, 0) for c in EXPENSE_CATEGORIES},
        )
