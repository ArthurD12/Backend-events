"""Ensamblaje de dependencias del módulo reporting."""

from local_eventos.modules.reporting.application.ports.clock import Clock
from local_eventos.modules.reporting.application.ports.event_staff import EventStaffLookup
from local_eventos.modules.reporting.application.ports.workers import WorkersReportLookup
from local_eventos.modules.reporting.infrastructure.clock import SystemClock
from local_eventos.modules.reporting.infrastructure.no_event_staff import NoEventStaff
from local_eventos.modules.reporting.infrastructure.no_workers import no_workers


def event_staff() -> EventStaffLookup:
    """Personal del evento. Nulo hasta que `staff.public_api` publique las asignaciones."""
    return NoEventStaff()


def workers_report() -> WorkersReportLookup | None:
    """Trabajadores para el reporte de personal. `None` hasta que `staff` publique la consulta."""
    return no_workers()


def clock() -> Clock:
    return SystemClock()
