"""Adaptador nulo de `EventStaffLookup`: `staff` todavía no expone asignaciones (HU17)."""

from uuid import UUID

from local_eventos.modules.reporting.application.ports.event_staff import StaffAssignment


class NoEventStaff:
    async def __call__(self, event_id: UUID) -> list[StaffAssignment] | None:
        return None
