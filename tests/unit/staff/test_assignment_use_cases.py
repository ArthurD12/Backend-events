"""Pruebas del puerto, los DTOs y los errores de asignaciones (HU17, T-05).

Todavía no existen casos de uso (T-07..T-10); aquí se verifica que el contrato
`AssignmentRepository` se pueda implementar en memoria y que los DTOs de lectura
sean inmutables y los códigos de error estables para la API. Sin base de datos.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, time
from uuid import UUID

import pytest

from local_eventos.modules.commercial.public_api import EventStatus
from local_eventos.modules.staff.application.errors import (
    AssignmentConflict,
    AssignmentImmutableError,
    AssignmentNotFoundError,
    AssignmentOverlapError,
    EventNotAssignableError,
    EventNotFoundError,
    StaffApplicationError,
    WorkerHasFutureAssignmentsError,
    WorkerInactiveError,
)
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentOverlap,
    AssignmentRepository,
    AssignmentView,
    EventAssignment,
)
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import AssignmentAudit
from local_eventos.modules.staff.domain.enums import AssignmentStatus, WorkerFunction

WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
ASSIGNMENT_ID = UUID("33333333-3333-3333-3333-333333333333")
OTHER_ASSIGNMENT_ID = UUID("44444444-4444-4444-4444-444444444444")
EVENT_ID = UUID("55555555-5555-5555-5555-555555555555")
OTHER_EVENT_ID = UUID("66666666-6666-6666-6666-666666666666")

START_AT = datetime(2026, 12, 1, 18, 0, tzinfo=UTC)
END_AT = datetime(2026, 12, 1, 23, 0, tzinfo=UTC)


class FakeAssignmentRepository:
    """Repositorio en memoria con la misma semántica que el puerto."""

    def __init__(self) -> None:
        self.assignments: dict[UUID, Assignment] = {}
        self.views: dict[UUID, AssignmentView] = {}
        self.audits: list[AssignmentAudit] = []
        self.locked_workers: list[UUID] = []

    async def lock_worker(self, worker_id: UUID) -> None:
        self.locked_workers.append(worker_id)

    async def save(self, assignment: Assignment, audit: AssignmentAudit) -> None:
        self.assignments[assignment.id] = assignment
        self.audits.append(audit)

    async def get(self, assignment_id: UUID) -> Assignment | None:
        return self.assignments.get(assignment_id)

    async def get_for_update(self, assignment_id: UUID) -> Assignment | None:
        return self.assignments.get(assignment_id)

    async def list_active_overlaps(
        self,
        worker_id: UUID,
        start_at: datetime,
        end_at: datetime,
        *,
        exclude_assignment_id: UUID | None = None,
    ) -> list[AssignmentOverlap]:
        overlaps = [
            AssignmentOverlap(
                id=assignment.id,
                event_id=assignment.event_id,
                start_at=assignment.start_at,
                end_at=assignment.end_at,
            )
            for assignment in self.assignments.values()
            if assignment.worker_id == worker_id
            and assignment.status is AssignmentStatus.ACTIVE
            and assignment.occupies
            and assignment.id != exclude_assignment_id
            and assignment.start_at < end_at
            and assignment.end_at > start_at
        ]
        return overlaps

    async def list_by_event(self, event_id: UUID) -> list[AssignmentView]:
        views = [
            view
            for view in self.views.values()
            if view.event_id == event_id and view.status is AssignmentStatus.ACTIVE
        ]
        return sorted(views, key=lambda view: view.start_at)

    async def list_occupying(self, worker_id: UUID) -> list[Assignment]:
        return [
            assignment
            for assignment in self.assignments.values()
            if assignment.worker_id == worker_id and assignment.occupies
        ]

    async def release(self, assignments: Sequence[Assignment]) -> None:
        for assignment in assignments:
            assignment.release()

    async def has_active_ending_after(self, worker_id: UUID, moment: datetime) -> bool:
        return any(
            assignment.worker_id == worker_id
            and assignment.status is AssignmentStatus.ACTIVE
            and assignment.occupies
            and assignment.end_at > moment
            for assignment in self.assignments.values()
        )

    async def get_view(self, assignment_id: UUID) -> AssignmentView | None:
        return self.views.get(assignment_id)


def _assignment(*, worker_id: UUID = WORKER_ID, event_id: UUID = EVENT_ID) -> Assignment:
    return Assignment.register(
        event_id=event_id,
        worker_id=worker_id,
        function=WorkerFunction.WAITER,
        start_at=START_AT,
        end_at=END_AT,
        pay=4500,
        assignment_id=ASSIGNMENT_ID,
    )


def _view() -> AssignmentView:
    return AssignmentView(
        id=ASSIGNMENT_ID,
        event_id=EVENT_ID,
        worker_id=WORKER_ID,
        worker_name="Ana Pérez",
        function=WorkerFunction.WAITER,
        function_description=None,
        start_at=START_AT,
        end_at=END_AT,
        pay_cents=4500,
        currency="PEN",
        status=AssignmentStatus.ACTIVE,
        event_code="EVT-2026-0012",
        event_status=EventStatus.CONFIRMED,
    )


def test_fake_implementa_el_puerto() -> None:
    repository: AssignmentRepository = FakeAssignmentRepository()
    assert repository is not None


async def test_fake_guarda_y_detecta_solapes() -> None:
    repository = FakeAssignmentRepository()
    assignment = _assignment()
    await repository.save(assignment, _audit())

    assert await repository.get(assignment.id) is assignment
    assert await repository.lock_worker(WORKER_ID) is None
    assert repository.locked_workers == [WORKER_ID]

    overlaps = await repository.list_active_overlaps(
        WORKER_ID,
        START_AT,
        END_AT,
    )
    assert [overlap.id for overlap in overlaps] == [ASSIGNMENT_ID]
    assert (
        await repository.list_active_overlaps(
            WORKER_ID,
            START_AT,
            END_AT,
            exclude_assignment_id=ASSIGNMENT_ID,
        )
        == []
    )
    assert await repository.list_active_overlaps(OTHER_WORKER_ID, START_AT, END_AT) == []


async def test_fake_libera_sin_cambiar_estado() -> None:
    repository = FakeAssignmentRepository()
    assignment = _assignment()
    await repository.save(assignment, _audit())

    await repository.release([assignment])

    assert assignment.occupies is False
    assert assignment.status is AssignmentStatus.ACTIVE
    assert await repository.list_occupying(WORKER_ID) == []
    assert await repository.has_active_ending_after(WORKER_ID, START_AT) is False


def _audit() -> AssignmentAudit:
    return AssignmentAudit.created(
        assignment_id=ASSIGNMENT_ID,
        actor_id=UUID("77777777-7777-7777-7777-777777777777"),
        occurred_at=START_AT,
    )


def test_assignment_view_es_inmutable() -> None:
    view = _view()

    assert view.event_code == "EVT-2026-0012"
    assert view.event_status is EventStatus.CONFIRMED
    assert view.pay_cents == 4500
    with pytest.raises(FrozenInstanceError):
        view.pay_cents = 5000  # type: ignore[misc]


def test_assignment_overlap_solo_lleva_lo_necesario() -> None:
    overlap = AssignmentOverlap(
        id=OTHER_ASSIGNMENT_ID,
        event_id=OTHER_EVENT_ID,
        start_at=START_AT,
        end_at=END_AT,
    )

    assert overlap.id == OTHER_ASSIGNMENT_ID
    assert overlap.event_id == OTHER_EVENT_ID
    with pytest.raises(FrozenInstanceError):
        overlap.event_id = EVENT_ID  # type: ignore[misc]


def test_event_assignment_no_expone_pago() -> None:
    event_assignment = EventAssignment(
        worker_id=WORKER_ID,
        worker_name="Ana Pérez",
        function=WorkerFunction.WAITER,
        function_description=None,
        starts_at=START_AT,
        ends_at=END_AT,
    )

    assert not hasattr(event_assignment, "pay_cents")
    assert not hasattr(event_assignment, "currency")
    with pytest.raises(FrozenInstanceError):
        event_assignment.worker_name = "Otro"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (AssignmentNotFoundError(), "staff.assignment_not_found"),
        (EventNotFoundError(), "staff.event_not_found"),
        (WorkerInactiveError(), "staff.worker_inactive"),
        (EventNotAssignableError("FINISHED"), "staff.event_not_assignable"),
        (AssignmentImmutableError(), "staff.assignment_immutable"),
        (WorkerHasFutureAssignmentsError(), "staff.worker_has_future_assignments"),
        (AssignmentOverlapError(), "staff.assignment_overlap"),
    ],
)
def test_codigos_de_error_estables(error: StaffApplicationError, code: str) -> None:
    assert error.code == code


def test_evento_no_asignable_indica_el_estado() -> None:
    error = EventNotAssignableError("CANCELLED")

    assert "CANCELLED" in str(error)


def test_solape_enumera_varios_eventos_sin_datos_personales() -> None:
    conflicts = (
        AssignmentConflict(
            event_code="EVT-2026-0012",
            event_date=date(2026, 12, 1),
            start_time=time(18, 0),
            end_time=time(23, 0),
        ),
        AssignmentConflict(
            event_code="EVT-2026-0013",
            event_date=date(2026, 12, 2),
            start_time=time(9, 0),
            end_time=time(13, 30),
        ),
    )

    error = AssignmentOverlapError(conflicts)

    assert error.code == "staff.assignment_overlap"
    assert error.conflicts == conflicts
    message = str(error)
    assert "EVT-2026-0012 del 01/12/2026 de 18:00 a 23:00" in message
    assert "EVT-2026-0013 del 02/12/2026 de 09:00 a 13:30" in message
    assert "documento" not in message.lower()
    assert "teléfono" not in message.lower()


def test_solape_sin_detalle_tiene_mensaje_generico() -> None:
    error = AssignmentOverlapError()

    assert error.conflicts == ()
    assert "se superpone" in str(error)
