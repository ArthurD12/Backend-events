"""Casos de uso de personal, disponibilidad y asignaciones con piezas en memoria (HU15–HU17)."""

from dataclasses import dataclass, replace
from datetime import date, time
from uuid import UUID, uuid4

import pytest

from local_eventos.modules.staff.application.errors import (
    AssignmentNotFoundError,
    AssignmentOverlapError,
    DocumentTakenError,
    EventNotAssignableError,
    EventNotFoundError,
    UnavailabilityNotFoundError,
    WorkerInactiveError,
    WorkerNotFoundError,
    WorkerUnavailableError,
)
from local_eventos.modules.staff.application.ports.worker_repository import WorkerFilters
from local_eventos.modules.staff.application.use_cases.assignments import (
    AssignWorker,
    AssignWorkerCommand,
    ListEventAssignments,
    ReleaseEventAssignments,
    WithdrawAssignment,
)
from local_eventos.modules.staff.application.use_cases.unavailability import (
    AddUnavailability,
    CheckAvailability,
    ListUnavailability,
    RemoveUnavailability,
    UnavailabilityCommand,
)
from local_eventos.modules.staff.application.use_cases.workers import (
    GetWorker,
    ListWorkers,
    RegisterWorker,
    SetWorkerActive,
    UpdateWorker,
)
from local_eventos.modules.staff.domain.assignment import AssignmentStatus
from local_eventos.modules.staff.domain.availability import AvailabilityStatus
from local_eventos.modules.staff.domain.errors import StaffRuleError, StaffValidationError
from local_eventos.modules.staff.domain.period import Period
from local_eventos.modules.staff.domain.worker import (
    DocumentType,
    Worker,
    WorkerData,
    WorkerFunction,
    WorkerType,
)

from .fakes import (
    FakeClock,
    FakeEventLookup,
    InMemoryAssignmentRepository,
    InMemoryUnavailabilityRepository,
    InMemoryWorkerRepository,
)

DAY = date(2026, 12, 19)
USER = uuid4()


def _data(**changes: object) -> WorkerData:
    data = WorkerData(
        name="Rosa Huamán", document_type=DocumentType.DNI, document_number="44125896",
        phone="987654321", function=WorkerFunction.WAITER, worker_type=WorkerType.EVENTUAL,
        reference_rate_cents=12_000,
    )  # fmt: skip
    return replace(data, **changes)  # type: ignore[arg-type]


@dataclass
class Staff:
    workers: InMemoryWorkerRepository
    unavailability: InMemoryUnavailabilityRepository
    assignments: InMemoryAssignmentRepository
    events: FakeEventLookup
    clock: FakeClock

    async def worker(self, **changes: object) -> Worker:
        number = str(40_000_000 + len(self.workers.workers))
        data = _data(document_number=number, **changes)
        return await RegisterWorker(self.workers, self.clock)(data, created_by=USER)

    def assign(self) -> AssignWorker:
        return AssignWorker(
            self.workers, self.unavailability, self.assignments, self.events, self.clock
        )

    async def away(self, worker: Worker, start: time, end: time, day: date = DAY) -> None:
        await AddUnavailability(self.workers, self.unavailability, self.clock)(
            worker.id, UnavailabilityCommand(day, start, end), created_by=USER
        )


@pytest.fixture
def staff() -> Staff:
    return Staff(
        InMemoryWorkerRepository(), InMemoryUnavailabilityRepository(),
        InMemoryAssignmentRepository(), FakeEventLookup(), FakeClock(),
    )  # fmt: skip


# HU15 — Datos del personal


async def test_ca15_1_registra_y_consulta(staff: Staff) -> None:
    worker = await RegisterWorker(staff.workers, staff.clock)(_data(), created_by=USER)

    assert await GetWorker(staff.workers)(worker.id) == worker
    assert (worker.created_by, worker.created_at) == (USER, staff.clock.now())


async def test_ca15_2_documento_no_se_repite(staff: Staff) -> None:
    await RegisterWorker(staff.workers, staff.clock)(_data(), created_by=USER)

    with pytest.raises(DocumentTakenError) as error:
        await RegisterWorker(staff.workers, staff.clock)(_data(name="Otra"), created_by=USER)
    assert error.value.code == "staff.document_taken"


async def test_ca15_3_modifica_y_el_documento_solo_si_no_es_de_otro(staff: Staff) -> None:
    rosa = await staff.worker()
    luis = await staff.worker(name="Luis Quispe")
    update = UpdateWorker(staff.workers, staff.clock)
    staff.clock.advance(hours=1)

    same_document = await update(
        rosa.id, _data(document_number=rosa.document.number, phone="999888777"), updated_by=luis.id
    )
    with pytest.raises(DocumentTakenError):
        await update(rosa.id, _data(document_number=luis.document.number), updated_by=USER)
    with pytest.raises(WorkerNotFoundError):
        await update(uuid4(), _data(), updated_by=USER)

    assert same_document.phone == "999888777"
    assert (same_document.updated_by, same_document.updated_at) == (luis.id, staff.clock.now())
    assert (await GetWorker(staff.workers)(rosa.id)).document == rosa.document


async def test_ca15_4_activa_y_desactiva(staff: Staff) -> None:
    worker = await staff.worker()
    set_active = SetWorkerActive(staff.workers, staff.clock)

    assert (await set_active(worker.id, False, updated_by=USER)).active is False
    assert (await set_active(worker.id, True, updated_by=USER)).active is True
    with pytest.raises(WorkerNotFoundError) as error:
        await set_active(uuid4(), False, updated_by=USER)
    assert error.value.code == "staff.worker_not_found"


async def test_ca15_6_filtra_por_funcion_tipo_estado_y_texto(staff: Staff) -> None:
    rosa = await staff.worker(name="Rosa Huamán")
    jose = await staff.worker(name="José Ramírez", function=WorkerFunction.COOK)
    ana = await staff.worker(name="Ana Torres", worker_type=WorkerType.FIXED)
    await SetWorkerActive(staff.workers, staff.clock)(ana.id, False, updated_by=USER)
    search = ListWorkers(staff.workers)

    assert [w.name for w in await search(WorkerFilters())] == [
        "Ana Torres",
        "José Ramírez",
        "Rosa Huamán",
    ]
    assert [w.id for w in await search(WorkerFilters(text="  jose  ramirez "))] == [jose.id]
    assert [w.id for w in await search(WorkerFilters(text=rosa.document.number))] == [rosa.id]
    assert [w.id for w in await search(WorkerFilters(function=WorkerFunction.COOK))] == [jose.id]
    assert [w.id for w in await search(WorkerFilters(worker_type=WorkerType.FIXED))] == [ana.id]
    assert [w.id for w in await search(WorkerFilters(active=False))] == [ana.id]


# HU16 — Disponibilidad


async def test_ca16_1_registra_lista_y_quita_indisponibilidad(staff: Staff) -> None:
    worker = await staff.worker()
    add = AddUnavailability(staff.workers, staff.unavailability, staff.clock)

    later = await add(
        worker.id, UnavailabilityCommand(DAY, time(22), time(2), " Viaje "), created_by=USER
    )
    earlier = await add(worker.id, UnavailabilityCommand(date(2026, 12, 1), time(8), time(12)),
                        created_by=USER)  # fmt: skip
    listed = await ListUnavailability(staff.workers, staff.unavailability)(worker.id)
    await RemoveUnavailability(staff.unavailability)(later.id)

    assert later.reason == "Viaje"
    assert later.period == Period.on(DAY, time(22), time(2))
    assert [u.id for u in listed] == [earlier.id, later.id]
    assert list(staff.unavailability.items) == [earlier.id]
    with pytest.raises(UnavailabilityNotFoundError):
        await RemoveUnavailability(staff.unavailability)(later.id)
    with pytest.raises(WorkerNotFoundError):
        await add(uuid4(), UnavailabilityCommand(DAY, time(8), time(9)), created_by=USER)
    with pytest.raises(StaffValidationError):
        await add(worker.id, UnavailabilityCommand(DAY, time(8), time(8)), created_by=USER)


async def test_ca16_2_a_4_consulta_libre_ocupado_y_no_disponible(staff: Staff) -> None:
    event = staff.events.add("EVT-2026-0007", start=time(18), end=time(23))
    free = await staff.worker(name="Ana Torres")
    busy = await staff.worker(name="Bruno Díaz")
    away = await staff.worker(name="Carla Ruiz")
    both = await staff.worker(name="Diego Paz")
    cook = await staff.worker(name="Elena Soto", function=WorkerFunction.COOK)
    inactive = await staff.worker(name="Fabio Gil")
    await SetWorkerActive(staff.workers, staff.clock)(inactive.id, False, updated_by=USER)
    for worker in (busy, both):
        await staff.assign()(event.id, AssignWorkerCommand(worker.id), created_by=USER)
    for worker in (away, both):
        await staff.away(worker, time(21), time(1))
    check = CheckAvailability(staff.workers, staff.unavailability, staff.assignments)

    result = await check(DAY, time(20), time(2))
    cooks = await check(DAY, time(20), time(2), WorkerFunction.COOK)

    assert [(a.worker.id, a.status, a.event_code) for a in result] == [
        (free.id, AvailabilityStatus.FREE, None),
        (busy.id, AvailabilityStatus.BUSY, "EVT-2026-0007"),
        (away.id, AvailabilityStatus.UNAVAILABLE, None),
        (both.id, AvailabilityStatus.BUSY, "EVT-2026-0007"),
        (cook.id, AvailabilityStatus.FREE, None),
    ]
    assert result[1].period == Period.on(DAY, time(18), time(23))
    assert [a.worker.id for a in cooks] == [cook.id]


# HU17 — Asignaciones


async def test_ca17_1_y_2_asigna_con_el_horario_y_la_tarifa_por_defecto(staff: Staff) -> None:
    event = staff.events.add(status="CONFIRMED")
    worker = await staff.worker()

    assigned = await staff.assign()(event.id, AssignWorkerCommand(worker.id), created_by=USER)

    assignment = assigned.assignment
    assert assigned.worker_name == "Rosa Huamán"
    assert (assignment.event_id, assignment.event_code) == (event.id, "EVT-2026-0001")
    assert assignment.function is WorkerFunction.WAITER
    assert assignment.period == Period.on(DAY, time(20), time(3))
    assert assignment.agreed_pay_cents == 12_000
    assert assignment.status is AssignmentStatus.ACTIVE
    assert (assignment.created_by, assignment.created_at) == (USER, staff.clock.now())


async def test_ca17_2_horario_funcion_y_pago_propios(staff: Staff) -> None:
    event = staff.events.add(status="IN_PROGRESS")
    worker = await staff.worker()

    assigned = await staff.assign()(
        event.id,
        AssignWorkerCommand(
            worker.id, function=WorkerFunction.SETUP, start_time=time(14), end_time=time(19),
            agreed_pay_cents=0,
        ),
        created_by=USER,
    )  # fmt: skip

    assert assigned.assignment.function is WorkerFunction.SETUP
    assert assigned.assignment.period == Period.on(DAY, time(14), time(19))
    assert assigned.assignment.agreed_pay_cents == 0  # R-STF-3: ayuda sin pago


@pytest.mark.parametrize("status", ["FINISHED", "CANCELLED"])
async def test_ca17_1_solo_eventos_programados_confirmados_o_en_ejecucion(
    staff: Staff, status: str
) -> None:
    event = staff.events.add(status=status)
    worker = await staff.worker()

    with pytest.raises(EventNotAssignableError) as error:
        await staff.assign()(event.id, AssignWorkerCommand(worker.id), created_by=USER)
    assert error.value.code == "staff.event_not_assignable"


async def test_errores_de_evento_y_trabajador_inexistentes(staff: Staff) -> None:
    event = staff.events.add()
    worker = await staff.worker()

    with pytest.raises(EventNotFoundError):
        await staff.assign()(uuid4(), AssignWorkerCommand(worker.id), created_by=USER)
    with pytest.raises(WorkerNotFoundError):
        await staff.assign()(event.id, AssignWorkerCommand(uuid4()), created_by=USER)


async def test_ca17_3_y_4_cruce_dice_el_evento_y_el_horario(staff: Staff) -> None:
    wedding = staff.events.add("EVT-2026-0001")
    party = staff.events.add("EVT-2026-0002", start=time(23), end=time(4))
    worker = await staff.worker()
    await staff.assign()(wedding.id, AssignWorkerCommand(worker.id), created_by=USER)

    with pytest.raises(AssignmentOverlapError) as error:
        await staff.assign()(party.id, AssignWorkerCommand(worker.id), created_by=USER)

    assert error.value.code == "staff.assignment_overlap"
    assert error.value.event_code == "EVT-2026-0001"
    assert str(error.value) == (
        "El trabajador ya está asignado a EVT-2026-0001 el 19/12/2026 de 20:00 a 03:00."
    )
    assert len(staff.assignments.items) == 1


async def test_r_stf_6_dos_asignaciones_en_el_mismo_evento_sin_cruce(staff: Staff) -> None:
    event = staff.events.add(start=time(18), end=time(23))
    worker = await staff.worker()
    assign = staff.assign()

    await assign(event.id, AssignWorkerCommand(worker.id, function=WorkerFunction.SETUP,
                 start_time=time(9), end_time=time(13)), created_by=USER)  # fmt: skip
    await assign(event.id, AssignWorkerCommand(worker.id, start_time=time(13)), created_by=USER)

    assert len(await ListEventAssignments(staff.assignments, staff.workers)(event.id)) == 2


async def test_ca17_5_inactivo_o_no_disponible(staff: Staff) -> None:
    event = staff.events.add()
    inactive = await staff.worker()
    await SetWorkerActive(staff.workers, staff.clock)(inactive.id, False, updated_by=USER)
    away = await staff.worker()
    await staff.away(away, time(0), time(21))

    with pytest.raises(WorkerInactiveError) as inactive_error:
        await staff.assign()(event.id, AssignWorkerCommand(inactive.id), created_by=USER)
    with pytest.raises(WorkerUnavailableError) as away_error:
        await staff.assign()(event.id, AssignWorkerCommand(away.id), created_by=USER)

    assert inactive_error.value.code == "staff.worker_inactive"
    assert away_error.value.code == "staff.worker_unavailable"
    assert "19/12/2026 de 00:00 a 21:00" in str(away_error.value)


async def test_pago_negativo_no_se_guarda(staff: Staff) -> None:
    event = staff.events.add()
    worker = await staff.worker()

    with pytest.raises(StaffValidationError):
        await staff.assign()(
            event.id, AssignWorkerCommand(worker.id, agreed_pay_cents=-1), created_by=USER
        )
    assert staff.assignments.items == {}


async def test_ca17_6_lista_las_asignaciones_del_evento(staff: Staff) -> None:
    event = staff.events.add()
    other = staff.events.add("EVT-2026-0002", day=date(2026, 12, 20))
    rosa = await staff.worker(name="Rosa Huamán")
    luis = await staff.worker(name="Luis Quispe")
    assign = staff.assign()
    await assign(event.id, AssignWorkerCommand(luis.id, start_time=time(21)), created_by=USER)
    await assign(event.id, AssignWorkerCommand(rosa.id), created_by=USER)
    await assign(other.id, AssignWorkerCommand(rosa.id), created_by=USER)

    listed = await ListEventAssignments(staff.assignments, staff.workers)(event.id)

    assert [(a.worker_name, a.assignment.period.local_start) for a in listed] == [
        ("Rosa Huamán", time(20)),
        ("Luis Quispe", time(21)),
    ]


async def test_ca17_7_retirar_libera_el_horario(staff: Staff) -> None:
    event = staff.events.add()
    worker = await staff.worker()
    assigned = await staff.assign()(event.id, AssignWorkerCommand(worker.id), created_by=USER)
    withdraw = WithdrawAssignment(staff.assignments, staff.clock)

    withdrawn = await withdraw(assigned.assignment.id, reason="Se enfermó", withdrawn_by=USER)
    again = await staff.assign()(event.id, AssignWorkerCommand(worker.id), created_by=USER)

    assert withdrawn.status is AssignmentStatus.WITHDRAWN
    assert withdrawn.withdrawal is not None
    assert (withdrawn.withdrawal.withdrawn_by, withdrawn.withdrawal.withdrawn_at) == (
        USER,
        staff.clock.now(),
    )
    assert again.assignment.is_active
    with pytest.raises(StaffRuleError) as error:
        await withdraw(assigned.assignment.id, reason=None, withdrawn_by=USER)
    assert error.value.code == "staff.assignment_already_withdrawn"
    with pytest.raises(AssignmentNotFoundError):
        await withdraw(uuid4(), reason=None, withdrawn_by=USER)


async def test_r_stf_5_liberar_las_asignaciones_de_un_evento(staff: Staff) -> None:
    event = staff.events.add()
    other = staff.events.add("EVT-2026-0002", day=date(2026, 12, 20))
    rosa, luis = await staff.worker(), await staff.worker(name="Luis Quispe")
    assign = staff.assign()
    first = await assign(event.id, AssignWorkerCommand(rosa.id), created_by=USER)
    await assign(event.id, AssignWorkerCommand(luis.id), created_by=USER)
    kept = await assign(other.id, AssignWorkerCommand(rosa.id), created_by=USER)
    await WithdrawAssignment(staff.assignments, staff.clock)(
        first.assignment.id, reason="Antes", withdrawn_by=USER
    )
    by: UUID = uuid4()

    released = await ReleaseEventAssignments(staff.assignments)(
        event.id, released_by=by, now=staff.clock.now()
    )

    listed = await ListEventAssignments(staff.assignments, staff.workers)(event.id)
    assert released == 1
    assert {a.assignment.status for a in listed} == {AssignmentStatus.WITHDRAWN}
    reasons = sorted(
        (a.assignment.withdrawal.reason or "") for a in listed if a.assignment.withdrawal
    )
    assert reasons == ["Antes", "Evento cancelado"]
    assert (await staff.assignments.get(kept.assignment.id)).is_active  # type: ignore[union-attr]
