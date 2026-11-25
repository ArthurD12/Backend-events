"""Flujo de caja y resultado por evento (HU22) con las consultas de otros módulos en memoria."""

from datetime import date
from uuid import UUID, uuid4

import pytest

from local_eventos.modules.commercial.public_api import EventFinance
from local_eventos.modules.identity.domain.permissions import Permission, Role, permissions_of
from local_eventos.modules.ledger.public_api import MonthlyCash, MovementCategory
from local_eventos.modules.reporting.application.errors import (
    ReportEventNotFoundError,
    ReportRangeInvalidError,
)
from local_eventos.modules.reporting.application.use_cases.cash_flow import GetCashFlow
from local_eventos.modules.reporting.application.use_cases.event_result import GetEventResult

S, ST, T, OE, OI = (
    MovementCategory.SUPPLIES,
    MovementCategory.STAFF,
    MovementCategory.TRANSPORT,
    MovementCategory.OTHER_EXPENSE,
    MovementCategory.OTHER_INCOME,
)


async def _months(date_from: date, date_to: date) -> list[MonthlyCash]:
    return [
        MonthlyCash(2026, 10, 300_000, 0, {S: 80_000, OI: 10_000}),
        MonthlyCash(2026, 11, 200_000, 50_000, {ST: 40_000, T: 5_000}),
    ]


def test_finance_read_solo_administrador() -> None:
    assert Permission.FINANCE_READ in permissions_of(Role.ADMIN)
    assert Permission.FINANCE_READ not in permissions_of(Role.EVENTS_MANAGER)
    assert Permission.FINANCE_READ not in permissions_of(Role.PURCHASING_MANAGER)


async def test_ca22_1_ca22_2_totales_por_categoria_y_por_mes() -> None:
    flow = await GetCashFlow(_months)(date(2026, 10, 1), date(2026, 11, 30))

    total = flow.summary
    assert (total.client_payments_cents, total.refunds_cents) == (450_000, 50_000)
    assert (total.other_income_cents, total.income_cents) == (10_000, 460_000)
    assert total.expenses_by_category == {S: 80_000, ST: 40_000, T: 5_000, OE: 0}
    assert (total.expense_cents, total.net_cents) == (125_000, 335_000)
    assert [(m.month, m.summary.net_cents) for m in flow.months] == [(10, 230_000), (11, 105_000)]


@pytest.mark.parametrize(
    ("date_from", "date_to"),
    [(date(2026, 11, 2), date(2026, 11, 1)), (date(2026, 1, 1), date(2027, 1, 2))],
)
async def test_rango_invalido(date_from: date, date_to: date) -> None:
    with pytest.raises(ReportRangeInvalidError) as error:
        await GetCashFlow(_months)(date_from, date_to)
    assert error.value.code == "report.range_invalid"


async def test_366_dias_se_permiten() -> None:
    flow = await GetCashFlow(_months)(date(2028, 1, 1), date(2028, 12, 31))
    assert flow.date_to == date(2028, 12, 31)


async def test_ca22_3_resultado_del_evento() -> None:
    event_id = uuid4()
    finance = EventFinance(
        event_id=event_id, event_code="EVT-2026-0001", event_date=date(2026, 12, 19),
        event_status="SCHEDULED", client_name="José", contract_id=uuid4(),
        contract_code="CON-2026-0001", total_cents=500_000, paid_cents=300_000,
        refunded_cents=20_000, balance_cents=220_000,
    )  # fmt: skip

    async def finance_lookup(wanted: UUID) -> EventFinance | None:
        return finance if wanted == event_id else None

    async def event_cash(wanted: UUID) -> dict[MovementCategory, int]:
        return {S: 90_000, ST: 60_000, OI: 5_000}

    result = await GetEventResult(finance_lookup, event_cash)(event_id)

    assert (result.collected_cents, result.expense_cents) == (280_000, 150_000)
    assert result.result_cents == 130_000
    assert result.expenses_by_category == {S: 90_000, ST: 60_000, T: 0, OE: 0}
    with pytest.raises(ReportEventNotFoundError):
        await GetEventResult(finance_lookup, event_cash)(uuid4())
