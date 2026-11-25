"""Forma del flujo de caja y del resultado por evento en la API (HU22)."""

from datetime import date
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.ledger.public_api import MovementCategory
from local_eventos.modules.reporting.application.use_cases.cash_flow import CashFlow, CashSummary
from local_eventos.modules.reporting.application.use_cases.event_result import EventResult


class ExpensesOut(BaseModel):
    supplies_cents: int
    staff_cents: int
    transport_cents: int
    other_cents: int


def _expenses(by_category: dict[MovementCategory, int]) -> ExpensesOut:
    return ExpensesOut(
        supplies_cents=by_category.get(MovementCategory.SUPPLIES, 0),
        staff_cents=by_category.get(MovementCategory.STAFF, 0),
        transport_cents=by_category.get(MovementCategory.TRANSPORT, 0),
        other_cents=by_category.get(MovementCategory.OTHER_EXPENSE, 0),
    )


class CashSummaryOut(BaseModel):
    client_payments_cents: int = Field(description="Pagos de clientes netos de devoluciones")
    refunds_cents: int
    other_income_cents: int
    income_cents: int
    expenses: ExpensesOut
    expense_cents: int
    net_cents: int = Field(description="Saldo del periodo: ingresos − egresos")

    @classmethod
    def from_summary(cls, summary: CashSummary) -> Self:
        return cls(
            client_payments_cents=summary.client_payments_cents,
            refunds_cents=summary.refunds_cents,
            other_income_cents=summary.other_income_cents,
            income_cents=summary.income_cents,
            expenses=_expenses(summary.expenses_by_category),
            expense_cents=summary.expense_cents,
            net_cents=summary.net_cents,
        )


class CashFlowMonthOut(CashSummaryOut):
    month: str = Field(description="AAAA-MM")


class CashFlowOut(BaseModel):
    date_from: date
    date_to: date
    currency: str = "PEN"
    totals: CashSummaryOut
    months: list[CashFlowMonthOut] = Field(description="Solo los meses con movimiento")

    @classmethod
    def from_flow(cls, flow: CashFlow) -> Self:
        return cls(
            date_from=flow.date_from,
            date_to=flow.date_to,
            totals=CashSummaryOut.from_summary(flow.summary),
            months=[
                CashFlowMonthOut(
                    month=f"{m.year:04d}-{m.month:02d}",
                    **CashSummaryOut.from_summary(m.summary).model_dump(),
                )
                for m in flow.months
            ],
        )


class EventResultOut(BaseModel):
    event_id: UUID
    event_code: str
    event_date: date
    event_status: str
    client_name: str
    contract_id: UUID
    contract_code: str
    currency: str = "PEN"
    total_cents: int = Field(description="Total contratado")
    balance_cents: int = Field(description="Saldo por cobrar (RN15)")
    collected_cents: int = Field(description="Cobrado al cliente, neto de devoluciones")
    expenses: ExpensesOut
    expense_cents: int
    result_cents: int = Field(description="Cobrado − egresos asociados al evento")

    @classmethod
    def from_result(cls, result: EventResult) -> Self:
        finance = result.finance
        return cls(
            event_id=finance.event_id,
            event_code=finance.event_code,
            event_date=finance.event_date,
            event_status=finance.event_status,
            client_name=finance.client_name,
            contract_id=finance.contract_id,
            contract_code=finance.contract_code,
            total_cents=finance.total_cents,
            balance_cents=finance.balance_cents,
            collected_cents=result.collected_cents,
            expenses=_expenses(result.expenses_by_category),
            expense_cents=result.expense_cents,
            result_cents=result.result_cents,
        )
