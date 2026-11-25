"""Ensamblaje de dependencias del módulo reporting."""

from local_eventos.modules.reporting.application.ports.event_staff import EventStaffLookup
from local_eventos.modules.reporting.infrastructure.no_event_staff import NoEventStaff


def event_staff() -> EventStaffLookup:
    """Personal del evento. Nulo hasta que `staff.public_api` publique las asignaciones."""
    return NoEventStaff()
