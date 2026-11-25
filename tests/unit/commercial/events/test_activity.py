"""Actividades y observaciones del evento (HU13): estados permitidos, transiciones y edición."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from local_eventos.modules.commercial.domain.events.activity import (
    ActivityAction,
    ActivityStatus,
    EventActivity,
    EventNote,
)
from local_eventos.modules.commercial.domain.events.event import (
    EventRuleError,
    EventStatus,
    EventValidationError,
)

from .test_event import _scheduled_event

NOW = datetime(2026, 11, 25, 15, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)


def _activity() -> EventActivity:
    return EventActivity.create(
        event_id=uuid4(), description="  Confirmar   la vajilla ", responsible_id=uuid4(),
        created_by=uuid4(), now=NOW,
    )  # fmt: skip


def test_ca13_1_actividad_nace_pendiente_con_auditoria() -> None:
    user, responsible = uuid4(), uuid4()

    activity = EventActivity.create(
        event_id=uuid4(), description="Llamar al local", responsible_id=responsible,
        created_by=user, now=NOW,
    )  # fmt: skip

    assert activity.status is ActivityStatus.PENDING
    assert (activity.description, activity.responsible_id) == ("Llamar al local", responsible)
    assert (activity.created_by, activity.created_at) == (user, NOW)
    assert (activity.completed_by, activity.completed_at) == (None, None)
    assert _activity().description == "Confirmar la vajilla"


@pytest.mark.parametrize("description", ["   ", "x" * 201])
def test_ca13_1_texto_obligatorio_hasta_200(description: str) -> None:
    with pytest.raises(EventValidationError) as error:
        EventActivity.create(
            event_id=uuid4(), description=description, responsible_id=uuid4(),
            created_by=uuid4(), now=NOW,
        )  # fmt: skip
    assert error.value.code == "activity.validation"


def test_ca13_3_completar_y_reabrir_dejan_historial() -> None:
    activity = _activity()
    user = uuid4()

    done = activity.complete(by=user, now=NOW)
    assert activity.status is ActivityStatus.DONE
    assert (activity.completed_by, activity.completed_at) == (user, NOW)
    reopened = activity.reopen(by=user, now=LATER)

    assert activity.status is ActivityStatus.PENDING
    assert (activity.completed_by, activity.completed_at) == (None, None)
    assert (done.activity_id, done.action, done.changed_by, done.changed_at) == (
        activity.id,
        ActivityAction.COMPLETED,
        user,
        NOW,
    )
    assert (reopened.action, reopened.changed_at) == (ActivityAction.REOPENED, LATER)


def test_ca13_3_no_se_repite_el_mismo_estado() -> None:
    activity = _activity()
    with pytest.raises(EventRuleError) as pending:
        activity.reopen(by=uuid4(), now=NOW)
    activity.complete(by=uuid4(), now=NOW)
    with pytest.raises(EventRuleError) as done:
        activity.complete(by=uuid4(), now=NOW)

    assert pending.value.code == "activity.already_pending"
    assert done.value.code == "activity.already_done"


def test_r_act_4_cambia_el_responsable() -> None:
    activity = _activity()
    other = uuid4()

    activity.change_responsible(other)

    assert activity.responsible_id == other


def test_ca13_4_observacion_con_auditoria_y_edicion() -> None:
    author, editor = uuid4(), uuid4()

    note = EventNote.create(
        event_id=uuid4(), text="  Faltan 20 copas.\nAvisar a compras. ", created_by=author, now=NOW
    )
    assert (note.text, note.created_by, note.created_at) == (
        "Faltan 20 copas.\nAvisar a compras.",
        author,
        NOW,
    )
    assert (note.edited_by, note.edited_at) == (None, None)
    note.edit("Faltan 30 copas.", by=editor, now=LATER)

    assert (note.text, note.edited_by, note.edited_at) == ("Faltan 30 copas.", editor, LATER)
    assert (note.created_by, note.created_at) == (author, NOW)


@pytest.mark.parametrize("text", ["  ", "x" * 1001])
def test_ca13_4_texto_obligatorio_hasta_1000(text: str) -> None:
    note = EventNote.create(event_id=uuid4(), text="Ok", created_by=uuid4(), now=NOW)

    with pytest.raises(EventValidationError) as created:
        EventNote.create(event_id=uuid4(), text=text, created_by=uuid4(), now=NOW)
    with pytest.raises(EventValidationError) as edited:
        note.edit(text, by=uuid4(), now=NOW)

    assert created.value.code == edited.value.code == "note.validation"
    assert note.text == "Ok"


def test_r_act_6_la_edita_su_autor_o_un_administrador() -> None:
    author = uuid4()
    note = EventNote.create(event_id=uuid4(), text="Ok", created_by=author, now=NOW)

    assert note.can_be_edited_by(author, is_admin=False)
    assert note.can_be_edited_by(uuid4(), is_admin=True)
    assert not note.can_be_edited_by(uuid4(), is_admin=False)


@pytest.mark.parametrize(
    ("status", "activities", "notes"),
    [
        (EventStatus.SCHEDULED, True, True),
        (EventStatus.CONFIRMED, True, True),
        (EventStatus.IN_PROGRESS, True, True),
        (EventStatus.FINISHED, False, True),
        (EventStatus.CANCELLED, False, False),
    ],
)
def test_r_act_2_estados_permitidos(status: EventStatus, activities: bool, notes: bool) -> None:
    event = _scheduled_event()
    event.status = status

    assert (event.can_manage_activities, event.can_take_notes) == (activities, notes)


def test_r_act_2_errores_por_estado() -> None:
    event = _scheduled_event()
    event.status = EventStatus.CANCELLED

    with pytest.raises(EventRuleError) as activities:
        event.check_activities_open()
    with pytest.raises(EventRuleError) as notes:
        event.check_notes_open()

    assert activities.value.code == "event.activities_closed"
    assert notes.value.code == "event.notes_closed"
