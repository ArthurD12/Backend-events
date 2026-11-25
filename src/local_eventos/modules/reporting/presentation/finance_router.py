"""Reportes financieros (HU22). Solo con `finance:read` (administrador; DOMAIN.md §9)."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from local_eventos.modules.identity.public_api import Permission, require_permission
from local_eventos.modules.reporting.application.use_cases.cash_flow import MAX_DAYS, GetCashFlow
from local_eventos.modules.reporting.application.use_cases.event_result import GetEventResult
from local_eventos.modules.reporting.presentation.dependencies import (
    CashTotalsDep,
    EventCashDep,
    EventFinanceDep,
)
from local_eventos.modules.reporting.presentation.finance_schemas import (
    CashFlowOut,
    EventResultOut,
)
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/reports",
    tags=["reportes"],
    dependencies=[Depends(require_permission(Permission.FINANCE_READ))],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)


@router.get(
    "/cash-flow",
    operation_id="reports_cash_flow",
    responses={422: {"model": Problem, "description": "`report.range_invalid`"}},
)
async def cash_flow(
    cash_totals: CashTotalsDep,
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to", description=f"Hasta {MAX_DAYS} días")],
) -> CashFlowOut:
    """Ingresos, egresos por categoría y saldo del periodo, por mes; sin anulados (CA-22.1)."""
    return CashFlowOut.from_flow(await GetCashFlow(cash_totals)(date_from, date_to))


@router.get(
    "/events/{event_id}/result",
    operation_id="reports_event_result",
    responses={404: {"model": Problem, "description": "`event.not_found`"}},
)
async def event_result(
    event_id: UUID, finance: EventFinanceDep, event_cash: EventCashDep
) -> EventResultOut:
    """Cobrado al cliente, egresos del evento por categoría y resultado (CA-22.3)."""
    return EventResultOut.from_result(await GetEventResult(finance, event_cash)(event_id))
