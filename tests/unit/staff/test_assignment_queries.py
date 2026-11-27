"""Pruebas de las consultas de asignaciones por evento y por id (HU17, T-10).

Cubren CA-17.12 (lista vigente ordenada con pago), CA-17.16 (el detalle incluye
anuladas) y CA-17.21 (consulta pública sin pago y lista vacía si no hay). Usan un
`AssignmentRepository` fake en memoria: sin base de datos.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from local_eventos.modules.commercial.public_api import EventInfo, EventStatus
from local_eventos.modules.staff.application.errors import (
    AssignmentNotFoundError,
    EventNotFoundError,
)
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentView,
)
from local_eventos.modules.staff.application.use_cases.get_assignment import (
    GetAssignment,
)
from local_eventos.modules.staff.application.use_cases.list_event_assignments import (
    ListEventAssignments,
)
from local_eventos.modules.staff.application.use_cases.list_event_assignments_for_sheet import (
    ListEventAssignmentsForSheet,
)
from local_eventos.modules.staff.domain.enums import AssignmentStatus, WorkerFunction

EVENT_ID = UUID("55555555-5555-5555-5555-555555555555")
OTHER_EVENT_ID = UUID("66666666-6666-6666-6666-666666666666")
ASSIGNMENT_ID = UUID("33333333-3333-3333-3333-333333333333")
OTHER_ASSIGNMENT_ID = UUID("44444444-4444-4444-4444-444444444444")
CANCELLED_ASSIGNMENT_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")

START_AT = datetime(2026, 12, 1, 23, 0, tzinfo=UTC)
END_AT = datetime(2026, 12, 2, 4, 0, tzinfo=UTC)
EARLIER_START_AT = datetime(2026, 12, 1, 20, 0, tzinfo=UTC)
EARLIER_END_AT = datetime(2026, 12, 1, 23, 0, tzinfo=UTC)


class FakeAssignmentRepository:
    """Repositorio en memoria con la semántica de `list_by_event` y `get_view`."""

    def __init__(self, views: list[AssignmentView] | None = None) -> None:
        self.views = {view.id: view for view in views or []}

    async def list_by_event(self, event_id: UUID) -> list[AssignmentView]:
        views = [
            view
            for view in self.views.values()
            if view.event_id == event_id and view.status is AssignmentStatus.ACTIVE
        ]
        return sorted(views, key=lambda view: view.start_at)

    async def get_view(self, assignment_id: UUID) -> AssignmentView | None:
        return self.views.get(assignment_id)


class FakeEventLookup:
    """Consulta de eventos en memoria con los datos de `EventInfo`."""

    def __init__(self, events: dict[UUID, EventInfo] | None = None) -> None:
        self.events = events if events is not None else {EVENT_ID: _event()}

    async def __call__(self, event_id: UUID) -> EventInfo | None:
        return self.events.get(event_id)


def _event(
    *,
    event_id: UUID = EVENT_ID,
    code: str = "EVT-2026-0012",
    status: EventStatus = EventStatus.CONFIRMED,
) -> EventInfo:
    return EventInfo(
        id=event_id,
        code=code,
        status=status,
        event_date=START_AT.date(),
        start_time=START_AT.time(),
        end_time=END_AT.time(),
    )


def _view(
    *,
    assignment_id: UUID = ASSIGNMENT_ID,
    worker_id: UUID = WORKER_ID,
    worker_name: str = "Ana Pérez",
    function: WorkerFunction = WorkerFunction.WAITER,
    function_description: str | None = None,
    start_at: datetime = START_AT,
    end_at: datetime = END_AT,
    pay_cents: int = 4500,
    status: AssignmentStatus = AssignmentStatus.ACTIVE,
    event_id: UUID = EVENT_ID,
    event_code: str = "EVT-2026-0012",
    event_status: EventStatus = EventStatus.CONFIRMED,
) -> AssignmentView:
    return AssignmentView(
        id=assignment_id,
        event_id=event_id,
        worker_id=worker_id,
        worker_name=worker_name,
        function=function,
        function_description=function_description,
        start_at=start_at,
        end_at=end_at,
        pay_cents=pay_cents,
        currency="PEN",
        status=status,
        event_code=event_code,
        event_status=event_status,
    )


# --- T-10: ListEventAssignments (CA-17.12) -----------------------------------


async def test_ca17_12_lista_ordenada_con_pago_y_estado_del_evento() -> None:
    later = _view()
    earlier = _view(
        assignment_id=OTHER_ASSIGNMENT_ID,
        worker_id=OTHER_WORKER_ID,
        worker_name="Luis Quispe",
        function=WorkerFunction.COOK,
        start_at=EARLIER_START_AT,
        end_at=EARLIER_END_AT,
        pay_cents=6000,
    )
    repository = FakeAssignmentRepository([later, earlier])
    use_case = ListEventAssignments(repository, FakeEventLookup())

    views = await use_case.execute(EVENT_ID)

    assert [view.id for view in views] == [OTHER_ASSIGNMENT_ID, ASSIGNMENT_ID]
    assert views[0].start_at < views[1].start_at
    assert views[0].worker_name == "Luis Quispe"
    assert views[1].pay_cents == 4500
    assert views[1].event_code == "EVT-2026-0012"
    assert views[1].event_status is EventStatus.CONFIRMED


async def test_ca17_16_la_lista_vigente_excluye_anuladas() -> None:
    active = _view()
    cancelled = _view(
        assignment_id=CANCELLED_ASSIGNMENT_ID,
        status=AssignmentStatus.CANCELLED,
    )
    repository = FakeAssignmentRepository([active, cancelled])
    use_case = ListEventAssignments(repository, FakeEventLookup())

    views = await use_case.execute(EVENT_ID)

    assert [view.id for view in views] == [ASSIGNMENT_ID]


async def test_ca17_12_evento_inexistente_lanza_event_not_found() -> None:
    repository = FakeAssignmentRepository([_view()])
    use_case = ListEventAssignments(repository, FakeEventLookup({}))

    with pytest.raises(EventNotFoundError) as error:
        await use_case.execute(EVENT_ID)

    assert error.value.code == "staff.event_not_found"


# --- T-10: GetAssignment (CA-17.16) ------------------------------------------


async def test_ca17_16_detalle_devuelve_activas_y_anuladas() -> None:
    active = _view()
    cancelled = _view(
        assignment_id=CANCELLED_ASSIGNMENT_ID,
        status=AssignmentStatus.CANCELLED,
    )
    use_case = GetAssignment(FakeAssignmentRepository([active, cancelled]))

    active_view = await use_case.execute(ASSIGNMENT_ID)
    cancelled_view = await use_case.execute(CANCELLED_ASSIGNMENT_ID)

    assert active_view.status is AssignmentStatus.ACTIVE
    assert cancelled_view.status is AssignmentStatus.CANCELLED
    assert cancelled_view.pay_cents == 4500


async def test_ca17_16_detalle_inexistente_lanza_assignment_not_found() -> None:
    use_case = GetAssignment(FakeAssignmentRepository())

    with pytest.raises(AssignmentNotFoundError) as error:
        await use_case.execute(ASSIGNMENT_ID)

    assert error.value.code == "staff.assignment_not_found"


# --- T-10: ListEventAssignmentsForSheet (CA-17.21) ---------------------------


async def test_ca17_21_lookup_para_ficha_no_expone_pago() -> None:
    later = _view()
    earlier = _view(
        assignment_id=OTHER_ASSIGNMENT_ID,
        worker_id=OTHER_WORKER_ID,
        worker_name="Luis Quispe",
        function=WorkerFunction.OTHER,
        function_description="Sonidista",
        start_at=EARLIER_START_AT,
        end_at=EARLIER_END_AT,
        pay_cents=6000,
    )
    use_case = ListEventAssignmentsForSheet(FakeAssignmentRepository([later, earlier]))

    assignments = await use_case.execute(EVENT_ID)

    assert [assignment.worker_id for assignment in assignments] == [
        OTHER_WORKER_ID,
        WORKER_ID,
    ]
    first = assignments[0]
    assert first.worker_name == "Luis Quispe"
    assert first.function is WorkerFunction.OTHER
    assert first.function_description == "Sonidista"
    assert first.starts_at == EARLIER_START_AT
    assert first.ends_at == EARLIER_END_AT
    for assignment in assignments:
        assert not hasattr(assignment, "pay_cents")
        assert not hasattr(assignment, "currency")


async def test_ca17_21_lookup_devuelve_lista_vacia_sin_asignaciones() -> None:
    use_case = ListEventAssignmentsForSheet(FakeAssignmentRepository())

    assignments = await use_case.execute(OTHER_EVENT_ID)

    assert assignments == []
