"""Personal designado del evento para la ficha (025): adaptador sobre `staff.public_api`."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from local_eventos.modules.reporting.infrastructure.event_staff import AssignmentsEventStaff
from local_eventos.modules.staff.public_api import EventAssignment, WorkerFunction

NOW = datetime(2026, 12, 1, 15, tzinfo=UTC)
EVENT = uuid4()


class _Assignments:
    def __init__(self) -> None:
        self.calls: list[UUID] = []

    async def __call__(self, event_id: UUID) -> list[EventAssignment]:
        self.calls.append(event_id)
        return [
            EventAssignment(uuid4(), "Pedro Quispe", WorkerFunction.WAITER, None, NOW, NOW),
            EventAssignment(uuid4(), "Ana Ruiz", WorkerFunction.OTHER, "Fotógrafa", NOW, NOW),
        ]


async def test_traduce_las_asignaciones_publicas_sin_datos_economicos() -> None:
    lookup = _Assignments()

    staff = await AssignmentsEventStaff(lookup)(EVENT)

    assert lookup.calls == [EVENT]
    assert [(s.worker_name, s.role, s.function) for s in staff] == [
        ("Pedro Quispe", "Mozo", WorkerFunction.WAITER),
        ("Ana Ruiz", "Fotógrafa", WorkerFunction.OTHER),
    ]
    assert not any(hasattr(s, name) for s in staff for name in ("pay_cents", "document", "rate"))
