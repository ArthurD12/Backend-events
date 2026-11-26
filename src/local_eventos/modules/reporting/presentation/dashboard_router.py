"""Endpoint del panel del administrador (HU31). Solo con el permiso `dashboard:read`."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from local_eventos.modules.identity.public_api import Permission, require_permission
from local_eventos.modules.reporting.application.use_cases.get_dashboard import GetDashboard
from local_eventos.modules.reporting.presentation.dashboard_schemas import DashboardOut
from local_eventos.modules.reporting.presentation.dependencies import (
    CashTotalsDep,
    OpenPurchasesDep,
    QuoteStatsDep,
    ReceivablesDep,
    StockReportDep,
    UpcomingEventsDep,
)
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/dashboard",
    tags=["panel"],
    dependencies=[Depends(require_permission(Permission.DASHBOARD_READ))],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)


@router.get("", operation_id="dashboard_get")
async def get_dashboard(
    quote_stats: QuoteStatsDep,
    cash_totals: CashTotalsDep,
    upcoming: UpcomingEventsDep,
    receivables: ReceivablesDep,
    stock: StockReportDep,
    purchases: OpenPurchasesDep,
    month: Annotated[
        str | None,
        Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="AAAA-MM; por defecto, el actual"),
    ] = None,
) -> DashboardOut:
    """Indicadores reales del negocio en una petición: cotizaciones, próximos eventos, caja del
    mes, cobros pendientes, alertas de almacén y compras abiertas (CA-31.1 a CA-31.11)."""
    year, number = (int(month[:4]), int(month[5:])) if month else (None, None)
    use_case = GetDashboard(quote_stats, cash_totals, upcoming, receivables, stock, purchases)
    return DashboardOut.from_dashboard(await use_case(year, number))
