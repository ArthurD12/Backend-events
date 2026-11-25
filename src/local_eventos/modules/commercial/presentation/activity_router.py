"""Endpoints de actividades y observaciones del evento (HU13).

Consultar exige `events:read` (los tres roles). Actividades: `events:manage` (administrador y
encargado de eventos). Observaciones: `event_notes:write` (los tres roles, R-ACT-5).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

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
from local_eventos.modules.commercial.presentation.activity_schemas import (
    ActivityIn,
    ActivityOut,
    ActivityResponsibleIn,
    NoteIn,
    NoteOut,
)
from local_eventos.modules.commercial.presentation.dependencies import (
    Coordinators,
    EventLog,
    Events,
    Today,
)
from local_eventos.modules.identity.public_api import (
    CurrentUser,
    Permission,
    get_current_user,
    require_permission,
)
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1",
    tags=["eventos"],
    dependencies=[Depends(require_permission(Permission.EVENTS_READ))],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

Reader = Annotated[CurrentUser, Depends(get_current_user)]
Manager = Annotated[CurrentUser, Depends(require_permission(Permission.EVENTS_MANAGE))]
NoteWriter = Annotated[CurrentUser, Depends(require_permission(Permission.EVENT_NOTES_WRITE))]

_ACTIVITY_CHANGE_ERRORS: dict[int | str, dict[str, object]] = {
    404: {"model": Problem, "description": "`activity.not_found`"},
    409: {"model": Problem, "description": "`event.activities_closed`, `activity.already_*`"},
}


async def _names(coordinators: Coordinators, user: CurrentUser) -> dict[UUID, str]:
    """Responsables posibles (identity.public_api) y quien consulta."""
    return {c.id: c.name for c in await coordinators()} | {user.id: user.name}


@router.get(
    "/events/{event_id}/activities",
    operation_id="events_activities_list",
    responses={404: {"model": Problem, "description": "`event.not_found`"}},
)
async def list_activities(
    event_id: UUID, user: Reader, events: Events, log: EventLog, coordinators: Coordinators
) -> list[ActivityOut]:
    """Actividades del evento por orden de creación (CA-13.5)."""
    activities = await ListActivities(events, log)(event_id)
    names = await _names(coordinators, user)
    return [ActivityOut.from_activity(a, names) for a in activities]


@router.post(
    "/events/{event_id}/activities",
    status_code=status.HTTP_201_CREATED,
    operation_id="events_activities_create",
    responses={
        404: {"model": Problem, "description": "`event.not_found`"},
        409: {"model": Problem, "description": "`event.activities_closed`"},
        422: {
            "model": Problem,
            "description": "`activity.validation`, `activity.responsible_invalid`",
        },
    },
)
async def create_activity(
    event_id: UUID,
    body: ActivityIn,
    user: Manager,
    events: Events,
    log: EventLog,
    coordinators: Coordinators,
    clock: Today,
) -> ActivityOut:
    """Registra una actividad o indicación pendiente (CA-13.1, R-ACT-4)."""
    activity = await AddActivity(events, log, coordinators, clock)(
        event_id,
        description=body.description,
        created_by=user.id,
        responsible_id=body.responsible_id,
    )
    return ActivityOut.from_activity(activity, await _names(coordinators, user))


@router.post(
    "/activities/{activity_id}/complete",
    operation_id="activities_complete",
    responses=_ACTIVITY_CHANGE_ERRORS,
)
async def complete_activity(
    activity_id: UUID,
    user: Manager,
    events: Events,
    log: EventLog,
    coordinators: Coordinators,
    clock: Today,
) -> ActivityOut:
    """Marca la actividad como completada (CA-13.3)."""
    activity = await CompleteActivity(events, log, clock)(activity_id, by=user.id)
    return ActivityOut.from_activity(activity, await _names(coordinators, user))


@router.post(
    "/activities/{activity_id}/reopen",
    operation_id="activities_reopen",
    responses=_ACTIVITY_CHANGE_ERRORS,
)
async def reopen_activity(
    activity_id: UUID,
    user: Manager,
    events: Events,
    log: EventLog,
    coordinators: Coordinators,
    clock: Today,
) -> ActivityOut:
    """Devuelve la actividad a pendiente (CA-13.3)."""
    activity = await ReopenActivity(events, log, clock)(activity_id, by=user.id)
    return ActivityOut.from_activity(activity, await _names(coordinators, user))


@router.put(
    "/activities/{activity_id}/responsible",
    operation_id="activities_responsible_update",
    responses={
        404: {"model": Problem, "description": "`activity.not_found`"},
        409: {"model": Problem, "description": "`event.activities_closed`"},
        422: {"model": Problem, "description": "`activity.responsible_invalid`"},
    },
)
async def change_responsible(
    activity_id: UUID,
    body: ActivityResponsibleIn,
    user: Manager,
    events: Events,
    log: EventLog,
    coordinators: Coordinators,
) -> ActivityOut:
    """Cambia el responsable de la actividad (R-ACT-4)."""
    activity = await ChangeActivityResponsible(events, log, coordinators)(
        activity_id, responsible_id=body.responsible_id
    )
    return ActivityOut.from_activity(activity, await _names(coordinators, user))


@router.get(
    "/events/{event_id}/notes",
    operation_id="events_notes_list",
    responses={404: {"model": Problem, "description": "`event.not_found`"}},
)
async def list_notes(
    event_id: UUID, user: Reader, events: Events, log: EventLog, coordinators: Coordinators
) -> list[NoteOut]:
    """Bitácora del evento, de la observación más reciente a la más antigua (CA-13.5)."""
    notes = await ListNotes(events, log)(event_id)
    names = await _names(coordinators, user)
    return [NoteOut.from_note(n, names) for n in notes]


@router.post(
    "/events/{event_id}/notes",
    status_code=status.HTTP_201_CREATED,
    operation_id="events_notes_create",
    responses={
        404: {"model": Problem, "description": "`event.not_found`"},
        409: {"model": Problem, "description": "`event.notes_closed`"},
        422: {"model": Problem, "description": "`note.validation`"},
    },
)
async def create_note(
    event_id: UUID,
    body: NoteIn,
    user: NoteWriter,
    events: Events,
    log: EventLog,
    coordinators: Coordinators,
    clock: Today,
) -> NoteOut:
    """Agrega una observación (CA-13.4); también con el evento finalizado (R-ACT-2)."""
    note = await AddNote(events, log, clock)(event_id, text=body.text, created_by=user.id)
    return NoteOut.from_note(note, await _names(coordinators, user))


@router.put(
    "/notes/{note_id}",
    operation_id="notes_update",
    responses={
        403: {"model": Problem, "description": "`auth.forbidden`, `note.not_author`"},
        404: {"model": Problem, "description": "`note.not_found`"},
        409: {"model": Problem, "description": "`event.notes_closed`"},
        422: {"model": Problem, "description": "`note.validation`"},
    },
)
async def update_note(
    note_id: UUID,
    body: NoteIn,
    user: NoteWriter,
    events: Events,
    log: EventLog,
    coordinators: Coordinators,
    clock: Today,
) -> NoteOut:
    """Edita una observación: su autor o quien tenga `event_notes:edit_any`, solo el
    administrador (R-ACT-1, R-ACT-6)."""
    note = await EditNote(events, log, clock)(
        note_id,
        text=body.text,
        editor_id=user.id,
        is_admin=Permission.EVENT_NOTES_EDIT_ANY in user.permissions,
    )
    return NoteOut.from_note(note, await _names(coordinators, user))
