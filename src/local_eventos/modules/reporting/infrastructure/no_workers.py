"""Sin consulta de trabajadores: `staff.public_api` todavía no la publica (COORDINACION §4)."""

from local_eventos.modules.reporting.application.ports.workers import WorkersReportLookup


def no_workers() -> WorkersReportLookup | None:
    """`None` deja el reporte de personal en `report.unavailable` (503)."""
    return None
