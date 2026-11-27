"""Ensamblaje de dependencias del módulo reporting."""

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.reporting.application.ports.clock import Clock
from local_eventos.modules.reporting.application.ports.event_staff import EventStaffLookup
from local_eventos.modules.reporting.application.ports.exporter import ReportExporter
from local_eventos.modules.reporting.application.ports.workers import WorkersReportLookup
from local_eventos.modules.reporting.infrastructure.clock import SystemClock
from local_eventos.modules.reporting.infrastructure.csv_exporter import CsvExporter
from local_eventos.modules.reporting.infrastructure.event_staff import AssignmentsEventStaff
from local_eventos.modules.reporting.infrastructure.no_workers import no_workers
from local_eventos.modules.reporting.infrastructure.pdf_exporter import PdfExporter
from local_eventos.modules.staff.public_api import event_assignments


def event_staff(session: AsyncSession) -> EventStaffLookup:
    """Personal designado del evento, por `staff.public_api` (sin pago)."""
    return AssignmentsEventStaff(event_assignments(session))


def workers_report() -> WorkersReportLookup | None:
    """Trabajadores para el reporte de personal. `None` hasta que `staff` publique la consulta."""
    return no_workers()


def clock() -> Clock:
    return SystemClock()


def csv_exporter() -> ReportExporter:
    return CsvExporter()


def pdf_exporter() -> ReportExporter:
    return PdfExporter()
