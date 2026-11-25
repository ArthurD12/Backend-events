"""Reportes con exportación (HU32–HU34). Cada ruta responde JSON, o descarga CSV o PDF con
`?format=csv|pdf`: las tres salidas salen de la misma `ReportTable` (CA-34.2).

Permisos (DOMAIN.md §9): eventos con `events:read` (montos solo con `payments:record`); caja
con `finance:read` (administrador); almacén con `inventory:read`; compras con
`purchasing:manage`; personal con `staff:manage`.
"""

from datetime import date, timedelta, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from local_eventos.modules.commercial.public_api import CompanyProfile, EventStatus
from local_eventos.modules.identity.public_api import CurrentUser, Permission, require_permission
from local_eventos.modules.inventory.public_api import Category, MovementKind
from local_eventos.modules.purchasing.public_api import PurchaseStatus
from local_eventos.modules.reporting.application.ports.exporter import ReportExporter
from local_eventos.modules.reporting.application.reports.cash import GetCashReport
from local_eventos.modules.reporting.application.reports.events import GetEventsReport
from local_eventos.modules.reporting.application.reports.inventory import (
    GetInventoryMovementsReport,
    GetStockReport,
)
from local_eventos.modules.reporting.application.reports.purchases import GetPurchasesReport
from local_eventos.modules.reporting.application.reports.staff import GetStaffReport
from local_eventos.modules.reporting.application.reports.table import MAX_DAYS, ReportTable
from local_eventos.modules.reporting.presentation.dependencies import (
    CashEntriesDep,
    ClockDep,
    CompanyDep,
    EventRefsDep,
    EventsReportDep,
    ExportersDep,
    MovementsReportDep,
    PurchasesReportDep,
    StockReportDep,
    WorkersReportDep,
)
from local_eventos.modules.reporting.presentation.report_schemas import ReportFormat, ReportOut
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/reports",
    tags=["reportes"],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

_LIMA = timezone(timedelta(hours=-5), "America/Lima")
_DOWNLOADS: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "El reporte en JSON o, con `format`, el archivo CSV o PDF",
        "content": {"text/csv": {}, "application/pdf": {}},
    }
}
_RANGE = {**_DOWNLOADS, 422: {"model": Problem, "description": "`report.range_invalid`"}}

From = Annotated[date, Query(alias="from", description="Desde (incluido)")]
To = Annotated[
    date, Query(alias="to", description=f"Hasta (incluido); como máximo {MAX_DAYS} días")
]
Format = Annotated[ReportFormat, Query(description="json (por defecto), csv o pdf")]


def _render(
    table: ReportTable,
    output: ReportFormat,
    exporters: dict[str, ReportExporter],
    company: CompanyProfile,
) -> ReportOut | Response:
    if output is ReportFormat.JSON:
        return ReportOut.from_table(table)
    exporter = exporters[output.value]
    day = table.generated_at.astimezone(_LIMA).date().isoformat()
    filename = f"reporte-{table.key.replace('_', '-')}-{day}.{exporter.extension}"
    return Response(
        content=exporter.export(table, company),
        media_type=exporter.media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/events", operation_id="reports_events", response_model=ReportOut, responses=_RANGE)
async def events_report(
    viewer: Annotated[CurrentUser, Depends(require_permission(Permission.EVENTS_READ))],
    events: EventsReportDep,
    clock: ClockDep,
    company: CompanyDep,
    exporters: ExportersDep,
    date_from: From,
    date_to: To,
    status: EventStatus | None = None,
    client_id: UUID | None = None,
    format: Format = ReportFormat.JSON,  # noqa: A002 - nombre del parámetro en la API
) -> ReportOut | Response:
    """CA-32.1: por fecha del evento, estado y cliente. Total contratado, pagado y saldo van
    vacíos (`null`) sin `payments:record`."""
    table = await GetEventsReport(events, clock)(
        date_from, date_to, status=status, client_id=client_id,
        include_amounts=Permission.PAYMENTS_RECORD in viewer.permissions,
    )  # fmt: skip
    return _render(table, format, exporters, company)


@router.get(
    "/cash",
    operation_id="reports_cash",
    response_model=ReportOut,
    responses=_RANGE,
    dependencies=[Depends(require_permission(Permission.FINANCE_READ))],
)
async def cash_report(
    entries: CashEntriesDep,
    refs: EventRefsDep,
    clock: ClockDep,
    company: CompanyDep,
    exporters: ExportersDep,
    date_from: From,
    date_to: To,
    format: Format = ReportFormat.JSON,  # noqa: A002
) -> ReportOut | Response:
    """CA-32.2: cada pago de cliente, devolución, ingreso y egreso; anulados marcados y fuera
    de los totales. Solo administrador."""
    table = await GetCashReport(entries, refs, clock)(date_from, date_to)
    return _render(table, format, exporters, company)


@router.get(
    "/inventory",
    operation_id="reports_inventory",
    response_model=ReportOut,
    responses=_DOWNLOADS,
    dependencies=[Depends(require_permission(Permission.INVENTORY_READ))],
)
async def inventory_report(
    stock: StockReportDep,
    clock: ClockDep,
    company: CompanyDep,
    exporters: ExportersDep,
    category: Category | None = None,
    include_inactive: bool = False,
    format: Format = ReportFormat.JSON,  # noqa: A002
) -> ReportOut | Response:
    """CA-32.3: stock actual por producto con costo promedio, valor y alertas."""
    table = await GetStockReport(stock, clock)(category, include_inactive=include_inactive)
    return _render(table, format, exporters, company)


@router.get(
    "/inventory-movements",
    operation_id="reports_inventory_movements",
    response_model=ReportOut,
    responses=_RANGE,
    dependencies=[Depends(require_permission(Permission.INVENTORY_READ))],
)
async def inventory_movements_report(
    movements: MovementsReportDep,
    refs: EventRefsDep,
    clock: ClockDep,
    company: CompanyDep,
    exporters: ExportersDep,
    date_from: From,
    date_to: To,
    kind: MovementKind | None = None,
    format: Format = ReportFormat.JSON,  # noqa: A002
) -> ReportOut | Response:
    """CA-32.3: movimientos de almacén del rango, por fecha del movimiento."""
    table = await GetInventoryMovementsReport(movements, refs, clock)(date_from, date_to, kind)
    return _render(table, format, exporters, company)


@router.get(
    "/purchases",
    operation_id="reports_purchases",
    response_model=ReportOut,
    responses=_RANGE,
    dependencies=[Depends(require_permission(Permission.PURCHASING_MANAGE))],
)
async def purchases_report(
    purchases: PurchasesReportDep,
    refs: EventRefsDep,
    clock: ClockDep,
    company: CompanyDep,
    exporters: ExportersDep,
    date_from: From,
    date_to: To,
    status: PurchaseStatus | None = None,
    format: Format = ReportFormat.JSON,  # noqa: A002
) -> ReportOut | Response:
    """CA-32.4: compras creadas en el rango (días de Lima), con proveedor, total y recepción."""
    table = await GetPurchasesReport(purchases, refs, clock)(date_from, date_to, status)
    return _render(table, format, exporters, company)


@router.get(
    "/staff",
    operation_id="reports_staff",
    response_model=ReportOut,
    responses={
        **_DOWNLOADS,
        503: {"model": Problem, "description": "`report.unavailable`"},
    },
    dependencies=[Depends(require_permission(Permission.STAFF_MANAGE))],
)
async def staff_report(
    workers: WorkersReportDep,
    clock: ClockDep,
    company: CompanyDep,
    exporters: ExportersDep,
    function: str | None = None,
    active: bool | None = None,
    format: Format = ReportFormat.JSON,  # noqa: A002
) -> ReportOut | Response:
    """CA-32.5: trabajadores con función, tipo, tarifa y estado. Responde 503
    `report.unavailable` hasta que `staff` publique su consulta de trabajadores."""
    table = await GetStaffReport(workers, clock)(function, active)
    return _render(table, format, exporters, company)
