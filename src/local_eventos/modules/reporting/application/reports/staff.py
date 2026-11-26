"""Reporte de personal (CA-32.5): trabajadores con función, tipo, tarifa y estado.

Depende de una consulta que `staff` todavía no publica (COORDINACION.md §4): sin ella, el
reporte responde `report.unavailable` en vez de mostrar una lista vacía que parezca real.
"""

from local_eventos.modules.reporting.application.errors import ReportUnavailableError
from local_eventos.modules.reporting.application.ports.clock import Clock
from local_eventos.modules.reporting.application.ports.workers import WorkersReportLookup
from local_eventos.modules.reporting.application.reports.table import (
    Column,
    ColumnType,
    Filter,
    ReportTable,
    Total,
)

COLUMNS = (
    Column("name", "Nombre"),
    Column("document", "Documento"),
    Column("function", "Función"),
    Column("kind", "Tipo"),
    Column("rate", "Tarifa", ColumnType.MONEY),
    Column("active", "Activo", ColumnType.BOOLEAN),
)


class GetStaffReport:
    def __init__(self, workers: WorkersReportLookup | None, clock: Clock) -> None:
        self._workers = workers
        self._clock = clock

    async def __call__(
        self, function: str | None = None, active: bool | None = None
    ) -> ReportTable:
        if self._workers is None:
            raise ReportUnavailableError("El reporte de personal")
        items = await self._workers(function, active)
        filters = []
        if function:
            filters.append(Filter("function", "Función", function))
        if active is not None:
            filters.append(Filter("active", "Estado", "Activos" if active else "Inactivos"))
        return ReportTable(
            key="staff",
            title="Reporte de personal",
            generated_at=self._clock.now(),
            filters=tuple(filters),
            columns=COLUMNS,
            rows=tuple(
                (w.name, w.document, w.function, w.kind, w.rate_cents, w.active) for w in items
            ),
            totals=(Total("workers", "Trabajadores", ColumnType.INTEGER, len(items)),),
        )
