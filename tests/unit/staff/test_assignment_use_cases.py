"""Pruebas del puerto, los DTOs, los errores y los casos de uso de asignaciones (HU17).

Cubre T-05 (contrato `AssignmentRepository` en memoria, DTOs y códigos de error) y
T-07 (`RegisterAssignment` con fakes de evento, trabajador y reloj). Sin base de datos.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, time
from inspect import signature
from uuid import UUID

import pytest

from local_eventos.modules.commercial.public_api import EventInfo, EventStatus
from local_eventos.modules.staff.application.assignment_occupancy import (
    AssignmentOccupancy,
)
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
    WorkerNotFoundError,
)
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentOverlap,
    AssignmentRepository,
    AssignmentView,
    EventAssignment,
)
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerLookup,
    WorkerRef,
)
from local_eventos.modules.staff.application.use_cases.cancel_assignment import (
    CancelAssignment,
)
from local_eventos.modules.staff.application.use_cases.register_assignment import (
    RegisterAssignment,
)
from local_eventos.modules.staff.application.use_cases.update_assignment import (
    UpdateAssignment,
)
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import (
    AssignmentAction,
    AssignmentAudit,
)
from local_eventos.modules.staff.domain.assignment_schedule import AssignmentSchedule
from local_eventos.modules.staff.domain.enums import (
    AssignmentStatus,
    WorkerFunction,
    WorkerStatus,
)
from local_eventos.modules.staff.domain.errors import (
    AssignmentDateInvalidError,
    AssignmentFunctionRequiredError,
    AssignmentReasonRequiredError,
)

WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
ASSIGNMENT_ID = UUID("33333333-3333-3333-3333-333333333333")
OTHER_ASSIGNMENT_ID = UUID("44444444-4444-4444-4444-444444444444")
EVENT_ID = UUID("55555555-5555-5555-5555-555555555555")
OTHER_EVENT_ID = UUID("66666666-6666-6666-6666-666666666666")
THIRD_EVENT_ID = UUID("88888888-8888-8888-8888-888888888888")
ACTOR_ID = UUID("99999999-9999-9999-9999-999999999999")

START_AT = datetime(2026, 12, 1, 18, 0, tzinfo=UTC)
END_AT = datetime(2026, 12, 1, 23, 0, tzinfo=UTC)
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)

EVENT_DATE = date(2026, 12, 1)


class FakeAssignmentRepository:
    """Repositorio en memoria con la misma semántica que el puerto."""

    def __init__(self) -> None:
        self.assignments: dict[UUID, Assignment] = {}
        self.views: dict[UUID, AssignmentView] = {}
        self.audits: list[AssignmentAudit] = []
        self.locked_workers: list[UUID] = []
        self.calls: list[str] = []

    async def lock_worker(self, worker_id: UUID) -> None:
        self.calls.append("lock_worker")
        self.locked_workers.append(worker_id)

    async def save(self, assignment: Assignment, audit: AssignmentAudit) -> None:
        self.calls.append("save")
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
        self.calls.append("list_active_overlaps")
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
        self.calls.append("list_occupying")
        return [
            assignment
            for assignment in self.assignments.values()
            if assignment.worker_id == worker_id and assignment.occupies
        ]

    async def release(self, assignments: Sequence[Assignment]) -> None:
        self.calls.append("release")
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


class FakeWorkerLookup:
    """Consulta de trabajadores en memoria; solo devuelve la referencia mínima."""

    def __init__(self, workers: dict[UUID, WorkerRef] | None = None) -> None:
        self.workers = workers if workers is not None else {WORKER_ID: _worker_ref()}

    async def get(self, worker_id: UUID) -> WorkerRef | None:
        return self.workers.get(worker_id)


class FakeEventLookup:
    """Consulta de eventos en memoria, con los mismos datos que `EventInfo`."""

    def __init__(self, events: dict[UUID, EventInfo] | None = None) -> None:
        self.events = events if events is not None else {EVENT_ID: _event()}

    async def __call__(self, event_id: UUID) -> EventInfo | None:
        return self.events.get(event_id)


class FakeClock:
    """Reloj fijo para auditorías deterministas."""

    def __init__(self, now: datetime = NOW) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _worker_ref(
    *,
    worker_id: UUID = WORKER_ID,
    function: WorkerFunction | None = WorkerFunction.WAITER,
    function_description: str | None = None,
    status: WorkerStatus = WorkerStatus.ACTIVE,
) -> WorkerRef:
    return WorkerRef(
        id=worker_id,
        name="Ana Pérez",
        function=function,
        function_description=function_description,
        status=status,
    )


def _event(
    *,
    event_id: UUID = EVENT_ID,
    code: str = "EVT-2026-0012",
    status: EventStatus = EventStatus.CONFIRMED,
    event_date: date = EVENT_DATE,
    start_time: time = time(18, 0),
    end_time: time = time(23, 0),
) -> EventInfo:
    return EventInfo(
        id=event_id,
        code=code,
        status=status,
        event_date=event_date,
        start_time=start_time,
        end_time=end_time,
    )


def _register(
    *,
    repository: FakeAssignmentRepository | None = None,
    workers: WorkerLookup | None = None,
    events: FakeEventLookup | None = None,
    clock: Clock | None = None,
) -> tuple[RegisterAssignment, FakeAssignmentRepository]:
    repo = repository if repository is not None else FakeAssignmentRepository()
    event_lookup = events if events is not None else FakeEventLookup()
    use_case = RegisterAssignment(
        assignments=repo,
        workers=workers if workers is not None else FakeWorkerLookup(),
        event_lookup=event_lookup,
        occupancy=AssignmentOccupancy(repo, event_lookup),
        clock=clock if clock is not None else FakeClock(),
    )
    return use_case, repo


def _execute(
    use_case: RegisterAssignment,
    *,
    event_id: UUID = EVENT_ID,
    worker_id: UUID = WORKER_ID,
    function: WorkerFunction | None = None,
    function_description: str | None = None,
    assignment_date: date = EVENT_DATE,
    start_time: time = time(18, 0),
    end_time: time = time(23, 0),
    pay_cents: int = 4500,
) -> Assignment:
    return use_case.execute(
        event_id=event_id,
        worker_id=worker_id,
        function=function,
        function_description=function_description,
        date=assignment_date,
        start_time=start_time,
        end_time=end_time,
        pay_cents=pay_cents,
        actor_id=ACTOR_ID,
    )


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


def _audit(assignment_id: UUID = ASSIGNMENT_ID) -> AssignmentAudit:
    return AssignmentAudit.created(
        assignment_id=assignment_id,
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


# --- T-07: RegisterAssignment -------------------------------------------------


def _existing(
    *,
    assignment_id: UUID,
    event_id: UUID,
    start_at: datetime,
    end_at: datetime,
    worker_id: UUID = WORKER_ID,
) -> Assignment:
    return Assignment.register(
        event_id=event_id,
        worker_id=worker_id,
        function=WorkerFunction.WAITER,
        start_at=start_at,
        end_at=end_at,
        pay=4000,
        assignment_id=assignment_id,
    )


async def test_ca17_1_alta_valida_y_auditoria_created() -> None:
    use_case, repository = _register()

    assignment = await _execute(use_case)

    assert assignment.status is AssignmentStatus.ACTIVE
    assert assignment.occupies is True
    assert assignment.event_id == EVENT_ID
    assert assignment.worker_id == WORKER_ID
    assert assignment.function is WorkerFunction.WAITER
    assert assignment.function_description is None
    assert assignment.pay.cents == 4500
    # 18:00 y 23:00 de America/Lima equivalen a 23:00 y 04:00 UTC.
    assert assignment.start_at == datetime(2026, 12, 1, 23, 0, tzinfo=UTC)
    assert assignment.end_at == datetime(2026, 12, 2, 4, 0, tzinfo=UTC)
    assert repository.assignments[assignment.id] is assignment

    assert len(repository.audits) == 1
    audit = repository.audits[0]
    assert audit.action is AssignmentAction.CREATED
    assert audit.assignment_id == assignment.id
    assert audit.actor_id == ACTOR_ID
    assert audit.occurred_at == NOW
    assert audit.reason is None
    assert audit.previous_values is None
    assert audit.new_values is None


async def test_evento_inexistente_lanza_event_not_found() -> None:
    use_case, repository = _register(events=FakeEventLookup({}))

    with pytest.raises(EventNotFoundError) as error:
        await _execute(use_case)

    assert error.value.code == "staff.event_not_found"
    assert repository.calls == []


@pytest.mark.parametrize("status", [EventStatus.FINISHED, EventStatus.CANCELLED])
async def test_ca17_3_evento_finalizado_o_cancelado_no_es_asignable(
    status: EventStatus,
) -> None:
    events = FakeEventLookup({EVENT_ID: _event(status=status)})
    use_case, repository = _register(events=events)

    with pytest.raises(EventNotAssignableError) as error:
        await _execute(use_case)

    assert status.value in str(error.value)
    assert repository.calls == []


async def test_trabajador_inexistente_lanza_worker_not_found() -> None:
    use_case, repository = _register(workers=FakeWorkerLookup({}))

    with pytest.raises(WorkerNotFoundError) as error:
        await _execute(use_case)

    assert error.value.code == "staff.not_found"
    assert repository.calls == []


async def test_ca17_2_trabajador_inactivo_es_rechazado() -> None:
    workers = FakeWorkerLookup({WORKER_ID: _worker_ref(status=WorkerStatus.INACTIVE)})
    use_case, repository = _register(workers=workers)

    with pytest.raises(WorkerInactiveError) as error:
        await _execute(use_case)

    assert error.value.code == "staff.worker_inactive"
    assert repository.calls == []


async def test_ca17_5_copia_funcion_y_descripcion_de_la_ficha() -> None:
    workers = FakeWorkerLookup(
        {
            WORKER_ID: _worker_ref(
                function=WorkerFunction.OTHER,
                function_description="Sonidista",
            )
        }
    )
    use_case, _repository = _register(workers=workers)

    assignment = await _execute(use_case, function=None)

    assert assignment.function is WorkerFunction.OTHER
    assert assignment.function_description == "Sonidista"


async def test_funcion_enviada_distinta_a_la_ficha_se_usa() -> None:
    workers = FakeWorkerLookup({WORKER_ID: _worker_ref(function=WorkerFunction.WAITER)})
    use_case, _repository = _register(workers=workers)

    assignment = await _execute(use_case, function=WorkerFunction.COOK)

    assert assignment.function is WorkerFunction.COOK
    assert assignment.function_description is None


async def test_ca17_26_funcion_obligatoria_si_la_ficha_no_tiene() -> None:
    workers = FakeWorkerLookup({WORKER_ID: _worker_ref(function=None)})
    use_case, repository = _register(workers=workers)

    with pytest.raises(AssignmentFunctionRequiredError) as error:
        await _execute(use_case, function=None)

    assert error.value.code == "staff.assignment_function_required"
    assert repository.calls == []


async def test_ca17_fecha_invalida_si_no_es_la_del_evento() -> None:
    use_case, repository = _register()

    with pytest.raises(AssignmentDateInvalidError) as error:
        await _execute(use_case, assignment_date=date(2026, 12, 2))

    assert error.value.code == "staff.assignment_date_invalid"
    assert repository.calls == []


async def test_fecha_del_dia_siguiente_permitida_si_el_evento_cruza_medianoche() -> None:
    events = FakeEventLookup({EVENT_ID: _event(start_time=time(20, 0), end_time=time(2, 0))})
    use_case, _repository = _register(events=events)

    assignment = await _execute(
        use_case,
        assignment_date=date(2026, 12, 2),
        start_time=time(0, 30),
        end_time=time(2, 0),
    )

    assert assignment.event_id == EVENT_ID


async def test_ca17_10_solape_con_un_evento_detalla_codigo_fecha_y_horario() -> None:
    repository = FakeAssignmentRepository()
    existing = _existing(
        assignment_id=OTHER_ASSIGNMENT_ID,
        event_id=OTHER_EVENT_ID,
        start_at=datetime(2026, 12, 1, 22, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 2, 4, 0, tzinfo=UTC),
    )
    await repository.save(existing, _audit(existing.id))
    events = FakeEventLookup(
        {
            EVENT_ID: _event(),
            OTHER_EVENT_ID: _event(
                event_id=OTHER_EVENT_ID,
                code="EVT-2026-0013",
                start_time=time(20, 0),
                end_time=time(2, 0),
            ),
        }
    )
    use_case, _repo = _register(repository=repository, events=events)

    with pytest.raises(AssignmentOverlapError) as error:
        await _execute(use_case)

    assert error.value.conflicts == (
        AssignmentConflict(
            event_code="EVT-2026-0013",
            event_date=EVENT_DATE,
            start_time=time(20, 0),
            end_time=time(2, 0),
        ),
    )
    assert "documento" not in str(error.value).lower()
    assert "teléfono" not in str(error.value).lower()


async def test_ca17_7_solape_con_dos_eventos_lista_ambos_conflictos() -> None:
    repository = FakeAssignmentRepository()
    first = _existing(
        assignment_id=OTHER_ASSIGNMENT_ID,
        event_id=OTHER_EVENT_ID,
        start_at=datetime(2026, 12, 1, 22, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 2, 4, 0, tzinfo=UTC),
    )
    second = _existing(
        assignment_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        event_id=THIRD_EVENT_ID,
        start_at=datetime(2026, 12, 2, 2, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 2, 6, 0, tzinfo=UTC),
    )
    await repository.save(first, _audit(first.id))
    await repository.save(second, _audit(second.id))
    events = FakeEventLookup(
        {
            EVENT_ID: _event(),
            OTHER_EVENT_ID: _event(
                event_id=OTHER_EVENT_ID,
                code="EVT-2026-0013",
                start_time=time(20, 0),
                end_time=time(2, 0),
            ),
            THIRD_EVENT_ID: _event(
                event_id=THIRD_EVENT_ID,
                code="EVT-2026-0014",
                event_date=date(2026, 12, 2),
                start_time=time(9, 0),
                end_time=time(13, 30),
            ),
        }
    )
    use_case, _repo = _register(repository=repository, events=events)

    with pytest.raises(AssignmentOverlapError) as error:
        await _execute(use_case)

    assert [conflict.event_code for conflict in error.value.conflicts] == [
        "EVT-2026-0013",
        "EVT-2026-0014",
    ]
    assert [conflict.event_date for conflict in error.value.conflicts] == [
        EVENT_DATE,
        date(2026, 12, 2),
    ]


async def test_ca17_20_libera_evento_cancelado_antes_de_comprobar_solapes() -> None:
    repository = FakeAssignmentRepository()
    existing = _existing(
        assignment_id=OTHER_ASSIGNMENT_ID,
        event_id=OTHER_EVENT_ID,
        start_at=datetime(2026, 12, 1, 22, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 2, 4, 0, tzinfo=UTC),
    )
    await repository.save(existing, _audit(existing.id))
    events = FakeEventLookup(
        {
            EVENT_ID: _event(),
            OTHER_EVENT_ID: _event(event_id=OTHER_EVENT_ID, status=EventStatus.CANCELLED),
        }
    )
    use_case, _repo = _register(repository=repository, events=events)

    assignment = await _execute(use_case)

    assert repository.assignments[existing.id].occupies is False
    assert repository.assignments[existing.id].status is AssignmentStatus.ACTIVE
    assert repository.assignments[assignment.id] is assignment
    assert repository.calls.index("release") < repository.calls.index("list_active_overlaps")


async def test_orden_de_bloqueo_liberacion_solape_y_guardado() -> None:
    use_case, repository = _register()

    await _execute(use_case)

    relevant = [
        call
        for call in repository.calls
        if call in {"lock_worker", "list_occupying", "list_active_overlaps", "save"}
    ]
    assert relevant == [
        "lock_worker",
        "list_occupying",
        "list_active_overlaps",
        "save",
    ]


# --- T-08: UpdateAssignment ---------------------------------------------------


def _existing_assignment(
    *,
    assignment_id: UUID = ASSIGNMENT_ID,
    event_id: UUID = EVENT_ID,
    worker_id: UUID = WORKER_ID,
    assignment_date: date = EVENT_DATE,
    start: time = time(18, 0),
    end: time = time(23, 0),
    pay_cents: int = 4000,
) -> Assignment:
    schedule = AssignmentSchedule(date=assignment_date, start_time=start, end_time=end)
    return Assignment.register(
        event_id=event_id,
        worker_id=worker_id,
        function=WorkerFunction.WAITER,
        start_at=schedule.start_at,
        end_at=schedule.end_at,
        pay=pay_cents,
        assignment_id=assignment_id,
    )


def _update(
    *,
    repository: FakeAssignmentRepository | None = None,
    workers: WorkerLookup | None = None,
    events: FakeEventLookup | None = None,
    clock: Clock | None = None,
) -> tuple[UpdateAssignment, FakeAssignmentRepository]:
    repo = repository if repository is not None else FakeAssignmentRepository()
    event_lookup = events if events is not None else FakeEventLookup()
    use_case = UpdateAssignment(
        assignments=repo,
        workers=workers if workers is not None else FakeWorkerLookup(),
        event_lookup=event_lookup,
        occupancy=AssignmentOccupancy(repo, event_lookup),
        clock=clock if clock is not None else FakeClock(),
    )
    return use_case, repo


async def _execute_update(
    use_case: UpdateAssignment,
    *,
    assignment_id: UUID = ASSIGNMENT_ID,
    function: WorkerFunction = WorkerFunction.WAITER,
    function_description: str | None = None,
    assignment_date: date = EVENT_DATE,
    start_time: time = time(18, 0),
    end_time: time = time(23, 0),
    pay_cents: int = 4000,
    reason: str = "Corrección del horario acordado",
) -> Assignment:
    return await use_case.execute(
        assignment_id=assignment_id,
        function=function,
        function_description=function_description,
        date=assignment_date,
        start_time=start_time,
        end_time=end_time,
        pay_cents=pay_cents,
        reason=reason,
        actor_id=ACTOR_ID,
    )


async def test_ca17_13_edicion_valida_audita_updated_con_snapshots() -> None:
    repository = FakeAssignmentRepository()
    existing = _existing_assignment()
    await repository.save(existing, _audit(existing.id))
    use_case, _repo = _update(repository=repository)

    assignment = await _execute_update(
        use_case,
        function=WorkerFunction.COOK,
        start_time=time(19, 0),
        end_time=time(22, 0),
        pay_cents=5000,
        reason="Cambio solicitado por el cliente",
    )

    assert assignment is existing
    assert assignment.function is WorkerFunction.COOK
    assert assignment.pay.cents == 5000
    assert assignment.start_at == datetime(2026, 12, 2, 0, 0, tzinfo=UTC)
    assert assignment.end_at == datetime(2026, 12, 2, 3, 0, tzinfo=UTC)

    assert len(repository.audits) == 2
    audit = repository.audits[-1]
    assert audit.action is AssignmentAction.UPDATED
    assert audit.assignment_id == ASSIGNMENT_ID
    assert audit.actor_id == ACTOR_ID
    assert audit.occurred_at == NOW
    assert audit.reason == "Cambio solicitado por el cliente"
    assert audit.previous_values is not None
    assert audit.new_values is not None
    assert audit.previous_values.function is WorkerFunction.WAITER
    assert audit.previous_values.pay_cents == 4000
    assert audit.new_values.function is WorkerFunction.COOK
    assert audit.new_values.pay_cents == 5000
    assert audit.new_values.start_at == assignment.start_at
    assert audit.new_values.end_at == assignment.end_at


async def test_ca17_13_noop_devuelve_asignacion_sin_auditoria() -> None:
    repository = FakeAssignmentRepository()
    existing = _existing_assignment()
    await repository.save(existing, _audit(existing.id))
    repository.calls.clear()
    use_case, _repo = _update(repository=repository)

    assignment = await _execute_update(use_case, pay_cents=4000)

    assert assignment is existing
    assert len(repository.audits) == 1
    assert "save" not in repository.calls


async def test_motivo_vacio_se_rechaza_antes_de_leer_o_bloquear() -> None:
    use_case, repository = _update()

    with pytest.raises(AssignmentReasonRequiredError) as error:
        await _execute_update(use_case, reason="   ")

    assert error.value.code == "staff.assignment_reason_required"
    assert repository.calls == []


async def test_editar_asignacion_inexistente_lanza_not_found() -> None:
    use_case, repository = _update()

    with pytest.raises(AssignmentNotFoundError) as error:
        await _execute_update(use_case)

    assert error.value.code == "staff.assignment_not_found"
    assert repository.calls == []


async def test_evento_inexistente_en_edicion_lanza_event_not_found() -> None:
    repository = FakeAssignmentRepository()
    existing = _existing_assignment()
    await repository.save(existing, _audit(existing.id))
    use_case, _repo = _update(repository=repository, events=FakeEventLookup({}))

    with pytest.raises(EventNotFoundError) as error:
        await _execute_update(use_case)

    assert error.value.code == "staff.event_not_found"


@pytest.mark.parametrize("status", [EventStatus.FINISHED, EventStatus.CANCELLED])
async def test_ca17_24_evento_finalizado_o_cancelado_es_solo_lectura(
    status: EventStatus,
) -> None:
    repository = FakeAssignmentRepository()
    existing = _existing_assignment()
    await repository.save(existing, _audit(existing.id))
    use_case, _repo = _update(
        repository=repository,
        events=FakeEventLookup({EVENT_ID: _event(status=status)}),
    )

    with pytest.raises(EventNotAssignableError) as error:
        await _execute_update(use_case, pay_cents=5000)

    assert error.value.code == "staff.event_not_assignable"
    assert status.value in str(error.value)
    assert len(repository.audits) == 1


async def test_trabajador_inactivo_con_fin_futuro_rechaza_edicion() -> None:
    repository = FakeAssignmentRepository()
    existing = _existing_assignment()
    await repository.save(existing, _audit(existing.id))
    workers = FakeWorkerLookup({WORKER_ID: _worker_ref(status=WorkerStatus.INACTIVE)})
    use_case, _repo = _update(repository=repository, workers=workers)

    with pytest.raises(WorkerInactiveError) as error:
        await _execute_update(use_case, pay_cents=5000)

    assert error.value.code == "staff.worker_inactive"
    assert existing.pay.cents == 4000
    assert len(repository.audits) == 1


async def test_trabajador_inactivo_permite_corregir_asignacion_pasada() -> None:
    repository = FakeAssignmentRepository()
    existing = _existing_assignment()
    await repository.save(existing, _audit(existing.id))
    workers = FakeWorkerLookup({WORKER_ID: _worker_ref(status=WorkerStatus.INACTIVE)})
    clock = FakeClock(datetime(2026, 12, 3, 12, 0, tzinfo=UTC))
    use_case, _repo = _update(repository=repository, workers=workers, clock=clock)

    assignment = await _execute_update(use_case, pay_cents=5000)

    assert assignment.pay.cents == 5000
    assert repository.audits[-1].action is AssignmentAction.UPDATED


async def test_ca17_14_solape_excluye_la_propia_asignacion() -> None:
    repository = FakeAssignmentRepository()
    existing = _existing_assignment()
    await repository.save(existing, _audit(existing.id))
    use_case, _repo = _update(repository=repository)

    assignment = await _execute_update(
        use_case,
        start_time=time(19, 0),
        end_time=time(22, 0),
    )

    assert assignment.start_at == datetime(2026, 12, 2, 0, 0, tzinfo=UTC)
    assert repository.audits[-1].action is AssignmentAction.UPDATED


async def test_ca17_14_solape_con_dos_eventos_detalla_ambos_conflictos() -> None:
    repository = FakeAssignmentRepository()
    own = _existing_assignment()
    await repository.save(own, _audit(own.id))
    first = _existing_assignment(
        assignment_id=OTHER_ASSIGNMENT_ID,
        event_id=OTHER_EVENT_ID,
        start=time(19, 0),
        end=time(23, 0),
    )
    second = _existing_assignment(
        assignment_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        event_id=THIRD_EVENT_ID,
        start=time(20, 0),
        end=time(1, 0),
    )
    await repository.save(first, _audit(first.id))
    await repository.save(second, _audit(second.id))
    events = FakeEventLookup(
        {
            EVENT_ID: _event(),
            OTHER_EVENT_ID: _event(
                event_id=OTHER_EVENT_ID,
                code="EVT-2026-0013",
                start_time=time(19, 0),
                end_time=time(23, 0),
            ),
            THIRD_EVENT_ID: _event(
                event_id=THIRD_EVENT_ID,
                code="EVT-2026-0014",
                start_time=time(20, 0),
                end_time=time(1, 0),
            ),
        }
    )
    use_case, _repo = _update(repository=repository, events=events)

    with pytest.raises(AssignmentOverlapError) as error:
        await _execute_update(
            use_case,
            start_time=time(19, 0),
            end_time=time(22, 0),
        )

    assert [conflict.event_code for conflict in error.value.conflicts] == [
        "EVT-2026-0013",
        "EVT-2026-0014",
    ]
    for conflict in error.value.conflicts:
        assert not hasattr(conflict, "worker_name")
        assert not hasattr(conflict, "pay_cents")
    assert "documento" not in str(error.value).lower()
    assert "teléfono" not in str(error.value).lower()
    assert own.start_at == datetime(2026, 12, 1, 23, 0, tzinfo=UTC)
    assert len(repository.audits) == 3


async def test_r_asg_11_editar_solo_pago_no_revalida_fecha_del_evento() -> None:
    repository = FakeAssignmentRepository()
    existing = _existing_assignment()
    await repository.save(existing, _audit(existing.id))
    # El evento se movió al 5 de diciembre; la asignación conserva el 1 de diciembre.
    events = FakeEventLookup({EVENT_ID: _event(event_date=date(2026, 12, 5))})
    use_case, _repo = _update(repository=repository, events=events)

    assignment = await _execute_update(use_case, pay_cents=5500)

    assert assignment.pay.cents == 5500
    assert assignment.start_at == existing.start_at
    audit = repository.audits[-1]
    assert audit.new_values is not None
    assert audit.new_values.pay_cents == 5500


async def test_ca17_15_worker_id_y_event_id_no_forman_parte_de_la_entrada() -> None:
    parameters = signature(UpdateAssignment.execute).parameters

    assert "worker_id" not in parameters
    assert "event_id" not in parameters
    assert set(parameters) == {
        "self",
        "assignment_id",
        "function",
        "function_description",
        "date",
        "start_time",
        "end_time",
        "pay_cents",
        "reason",
        "actor_id",
    }


# --- T-09: CancelAssignment ---------------------------------------------------


class _OrderRepository(FakeAssignmentRepository):
    """Registra el orden de bloqueo del trabajador y de la asignación."""

    async def lock_worker(self, worker_id: UUID) -> None:
        self.calls.append("lock_worker")
        await super().lock_worker(worker_id)

    async def get_for_update(self, assignment_id: UUID) -> Assignment | None:
        self.calls.append("get_for_update")
        return await super().get_for_update(assignment_id)


def _cancel(
    *,
    repository: FakeAssignmentRepository | None = None,
    events: FakeEventLookup | None = None,
    clock: Clock | None = None,
) -> tuple[CancelAssignment, FakeAssignmentRepository]:
    repo = repository if repository is not None else FakeAssignmentRepository()
    use_case = CancelAssignment(
        assignments=repo,
        event_lookup=events if events is not None else FakeEventLookup(),
        clock=clock if clock is not None else FakeClock(),
    )
    return use_case, repo


async def _execute_cancel(
    use_case: CancelAssignment,
    *,
    assignment_id: UUID = ASSIGNMENT_ID,
    reason: str = "El cliente canceló el evento",
) -> Assignment:
    return await use_case.execute(
        assignment_id=assignment_id,
        reason=reason,
        actor_id=ACTOR_ID,
    )


async def test_ca17_16_anular_libera_y_audita_cancelled_con_motivo() -> None:
    repository = FakeAssignmentRepository()
    existing = _existing_assignment()
    await repository.save(existing, _audit(existing.id))
    use_case, _repo = _cancel(repository=repository)

    assignment = await _execute_cancel(
        use_case,
        reason="El cliente canceló el evento",
    )

    assert assignment is existing
    assert assignment.status is AssignmentStatus.CANCELLED
    assert assignment.occupies is False
    assert repository.assignments[ASSIGNMENT_ID] is existing
    assert len(repository.audits) == 2
    audit = repository.audits[-1]
    assert audit.action is AssignmentAction.CANCELLED
    assert audit.assignment_id == ASSIGNMENT_ID
    assert audit.actor_id == ACTOR_ID
    assert audit.occurred_at == NOW
    assert audit.reason == "El cliente canceló el evento"
    assert audit.previous_values is None
    assert audit.new_values is None


async def test_anular_ya_cancelada_es_idempotente_sin_segunda_auditoria() -> None:
    repository = FakeAssignmentRepository()
    existing = _existing_assignment()
    existing.cancel()
    await repository.save(existing, _audit(existing.id))
    repository.calls.clear()
    use_case, _repo = _cancel(repository=repository)

    assignment = await _execute_cancel(use_case)

    assert assignment is existing
    assert assignment.status is AssignmentStatus.CANCELLED
    assert assignment.occupies is False
    assert len(repository.audits) == 1
    assert "save" not in repository.calls


async def test_ca17_16_motivo_vacio_se_rechaza_antes_de_leer_o_bloquear() -> None:
    use_case, repository = _cancel()

    with pytest.raises(AssignmentReasonRequiredError) as error:
        await _execute_cancel(use_case, reason="   ")

    assert error.value.code == "staff.assignment_reason_required"
    assert repository.calls == []


async def test_anular_asignacion_inexistente_lanza_not_found() -> None:
    use_case, repository = _cancel()

    with pytest.raises(AssignmentNotFoundError) as error:
        await _execute_cancel(use_case)

    assert error.value.code == "staff.assignment_not_found"
    assert repository.calls == []


async def test_anular_con_evento_inexistente_lanza_event_not_found() -> None:
    repository = FakeAssignmentRepository()
    existing = _existing_assignment()
    await repository.save(existing, _audit(existing.id))
    use_case, _repo = _cancel(repository=repository, events=FakeEventLookup({}))

    with pytest.raises(EventNotFoundError) as error:
        await _execute_cancel(use_case)

    assert error.value.code == "staff.event_not_found"
    assert existing.status is AssignmentStatus.ACTIVE
    assert existing.occupies is True
    assert len(repository.audits) == 1


@pytest.mark.parametrize("status", [EventStatus.FINISHED, EventStatus.CANCELLED])
async def test_ca17_24_anular_evento_finalizado_o_cancelado_es_rechazado(
    status: EventStatus,
) -> None:
    repository = FakeAssignmentRepository()
    existing = _existing_assignment()
    await repository.save(existing, _audit(existing.id))
    use_case, _repo = _cancel(
        repository=repository,
        events=FakeEventLookup({EVENT_ID: _event(status=status)}),
    )

    with pytest.raises(EventNotAssignableError) as error:
        await _execute_cancel(use_case)

    assert error.value.code == "staff.event_not_assignable"
    assert status.value in str(error.value)
    assert existing.status is AssignmentStatus.ACTIVE
    assert existing.occupies is True
    assert len(repository.audits) == 1


async def test_anular_bloquea_primero_trabajador_y_luego_asignacion() -> None:
    repository = _OrderRepository()
    existing = _existing_assignment()
    await repository.save(existing, _audit(existing.id))
    repository.calls.clear()
    use_case, _repo = _cancel(repository=repository)

    await _execute_cancel(use_case)

    assert repository.calls.index("lock_worker") < repository.calls.index("get_for_update")
    assert repository.locked_workers == [WORKER_ID]
