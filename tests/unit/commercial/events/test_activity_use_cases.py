"""Casos de uso de actividades y observaciones (HU13) con piezas en memoria."""

from dataclasses import dataclass
from uuid import uuid4

import pytest

from local_eventos.modules.commercial.application.events.errors import (
    ActivityNotFoundError,
    ActivityResponsibleInvalidError,
    EventNotFoundError,
    NoteNotAuthorError,
    NoteNotFoundError,
)
from local_eventos.modules.commercial.application.events.use_cases.activities import (
    AddActivity,
    AddNote,
    ChangeActivityResponsible,
    CompleteActivity,
    EditNote,
    ListActivities,
    ListNotes,
    ReopenActivity,
)
from local_eventos.modules.commercial.domain.events.activity import (
    ActivityAction,
    ActivityStatus,
)
from local_eventos.modules.commercial.domain.events.event import (
    Event,
    EventRuleError,
    EventStatus,
    EventValidationError,
)
from local_eventos.modules.identity.public_api import Coordinator
from tests.unit.commercial.quotes.fakes import FakeClock

from .fakes import FakeCoordinators, InMemoryEventLogRepository, InMemoryEventRepository
from .test_event import _scheduled_event

MANAGER = Coordinator(id=uuid4(), name="Rosa Huamán")
ADMIN = Coordinator(id=uuid4(), name="Harold Canaza")
PURCHASING = uuid4()  # compras y almacén: no puede ser responsable


@dataclass
class Setup:
    events: InMemoryEventRepository
    log: InMemoryEventLogRepository
    coordinators: FakeCoordinators
    clock: FakeClock
    event: Event

    def add(self) -> AddActivity:
        return AddActivity(self.events, self.log, self.coordinators, self.clock)

    def complete(self) -> CompleteActivity:
        return CompleteActivity(self.events, self.log, self.clock)

    def reopen(self) -> ReopenActivity:
        return ReopenActivity(self.events, self.log, self.clock)

    def responsible(self) -> ChangeActivityResponsible:
        return ChangeActivityResponsible(self.events, self.log, self.coordinators)

    def add_note(self) -> AddNote:
        return AddNote(self.events, self.log, self.clock)

    def edit_note(self) -> EditNote:
        return EditNote(self.events, self.log, self.clock)

    async def set_status(self, status: EventStatus) -> None:
        self.event.status = status
        await self.events.update(self.event)


@pytest.fixture
async def setup() -> Setup:
    events = InMemoryEventRepository()
    event = _scheduled_event()
    await events.add(event)
    return Setup(
        events, InMemoryEventLogRepository(), FakeCoordinators(MANAGER, ADMIN), FakeClock(), event
    )


async def test_ca13_1_registra_actividad_con_quien_crea_como_responsable(setup: Setup) -> None:
    activity = await setup.add()(
        setup.event.id, description="Confirmar vajilla", created_by=MANAGER.id
    )
    other = await setup.add()(
        setup.event.id, description="Llamar al local", created_by=MANAGER.id,
        responsible_id=ADMIN.id,
    )  # fmt: skip

    assert activity.status is ActivityStatus.PENDING
    assert (activity.responsible_id, activity.created_by) == (MANAGER.id, MANAGER.id)
    assert activity.created_at == setup.clock.now()
    assert other.responsible_id == ADMIN.id
    assert await ListActivities(setup.events, setup.log)(setup.event.id) == [activity, other]


async def test_ca13_1_errores_al_registrar(setup: Setup) -> None:
    with pytest.raises(ActivityResponsibleInvalidError):
        await setup.add()(
            setup.event.id, description="Ok", created_by=MANAGER.id, responsible_id=PURCHASING
        )
    with pytest.raises(EventValidationError) as invalid:
        await setup.add()(setup.event.id, description=" ", created_by=MANAGER.id)
    with pytest.raises(EventNotFoundError):
        await setup.add()(uuid4(), description="Ok", created_by=MANAGER.id)

    assert invalid.value.code == "activity.validation"
    assert setup.log.activities == {}


async def test_ca13_3_completar_y_reabrir_guardan_historial(setup: Setup) -> None:
    activity = await setup.add()(setup.event.id, description="Ok", created_by=MANAGER.id)

    done = await setup.complete()(activity.id, by=ADMIN.id)
    setup.clock.advance(minutes=5)
    with pytest.raises(EventRuleError) as twice:
        await setup.complete()(activity.id, by=ADMIN.id)
    reopened = await setup.reopen()(activity.id, by=MANAGER.id)

    assert (done.status, done.completed_by) == (ActivityStatus.DONE, ADMIN.id)
    assert twice.value.code == "activity.already_done"
    assert (reopened.status, reopened.completed_by) == (ActivityStatus.PENDING, None)
    changes = await setup.log.list_changes(activity.id)
    assert [(c.action, c.changed_by) for c in changes] == [
        (ActivityAction.COMPLETED, ADMIN.id),
        (ActivityAction.REOPENED, MANAGER.id),
    ]
    assert changes[1].changed_at > changes[0].changed_at


async def test_r_act_4_cambia_el_responsable(setup: Setup) -> None:
    activity = await setup.add()(setup.event.id, description="Ok", created_by=MANAGER.id)

    changed = await setup.responsible()(activity.id, responsible_id=ADMIN.id)
    with pytest.raises(ActivityResponsibleInvalidError):
        await setup.responsible()(activity.id, responsible_id=PURCHASING)
    with pytest.raises(ActivityNotFoundError):
        await setup.complete()(uuid4(), by=MANAGER.id)

    assert changed.responsible_id == ADMIN.id
    assert (await setup.log.get_activity(activity.id)) == changed


@pytest.mark.parametrize("status", [EventStatus.FINISHED, EventStatus.CANCELLED])
async def test_r_act_2_actividades_cerradas(setup: Setup, status: EventStatus) -> None:
    activity = await setup.add()(setup.event.id, description="Ok", created_by=MANAGER.id)
    await setup.set_status(status)

    attempts = [
        setup.add()(setup.event.id, description="Otra", created_by=MANAGER.id),
        setup.complete()(activity.id, by=MANAGER.id),
        setup.responsible()(activity.id, responsible_id=ADMIN.id),
    ]
    for attempt in attempts:
        with pytest.raises(EventRuleError) as error:
            await attempt
        assert error.value.code == "event.activities_closed"
    assert len(await ListActivities(setup.events, setup.log)(setup.event.id)) == 1


async def test_ca13_4_observaciones_de_la_mas_reciente_a_la_mas_antigua(setup: Setup) -> None:
    first = await setup.add_note()(
        setup.event.id, text="Cliente pide mesa extra", created_by=PURCHASING
    )
    setup.clock.advance(minutes=1)
    second = await setup.add_note()(setup.event.id, text="Faltan copas", created_by=MANAGER.id)

    notes = await ListNotes(setup.events, setup.log)(setup.event.id)

    assert notes == [second, first]
    assert (first.created_by, first.edited_by) == (PURCHASING, None)


async def test_r_act_1_y_6_edita_su_autor_o_un_administrador(setup: Setup) -> None:
    note = await setup.add_note()(setup.event.id, text="Faltan copas", created_by=PURCHASING)
    setup.clock.advance(minutes=1)

    own = await setup.edit_note()(
        note.id, text="Faltan 20 copas", editor_id=PURCHASING, is_admin=False
    )
    by_admin = await setup.edit_note()(
        note.id, text="Faltan 30 copas", editor_id=ADMIN.id, is_admin=True
    )
    with pytest.raises(NoteNotAuthorError):
        await setup.edit_note()(note.id, text="No", editor_id=MANAGER.id, is_admin=False)
    with pytest.raises(NoteNotFoundError):
        await setup.edit_note()(uuid4(), text="No", editor_id=ADMIN.id, is_admin=True)

    assert (own.text, own.edited_by, own.edited_at) == (
        "Faltan 20 copas",
        PURCHASING,
        setup.clock.now(),
    )
    assert (by_admin.text, by_admin.edited_by, by_admin.created_by) == (
        "Faltan 30 copas",
        ADMIN.id,
        PURCHASING,
    )


async def test_r_act_2_finalizado_acepta_observaciones_y_cancelado_no(setup: Setup) -> None:
    note = await setup.add_note()(setup.event.id, text="Antes", created_by=MANAGER.id)
    await setup.set_status(EventStatus.FINISHED)

    after = await setup.add_note()(setup.event.id, text="Después", created_by=MANAGER.id)
    edited = await setup.edit_note()(note.id, text="Editada", editor_id=MANAGER.id, is_admin=False)
    await setup.set_status(EventStatus.CANCELLED)
    with pytest.raises(EventRuleError) as added:
        await setup.add_note()(setup.event.id, text="No", created_by=MANAGER.id)
    with pytest.raises(EventRuleError) as changed:
        await setup.edit_note()(note.id, text="No", editor_id=MANAGER.id, is_admin=False)

    assert (after.text, edited.text) == ("Después", "Editada")
    assert added.value.code == changed.value.code == "event.notes_closed"
    assert len(await ListNotes(setup.events, setup.log)(setup.event.id)) == 2
