"""Endpoints de asignaciones de personal (HU17). Traducen HTTP ⇄ casos de uso.

Escritura (`POST`, `PUT`, `cancel`) exige `staff:assign` (solo administrador);
lectura (`GET` lista y detalle) exige `staff:manage` (administrador y encargado de
eventos); compras no tiene ninguno de los dos. No existe `DELETE`: la anulación es
lógica mediante `cancel` y un intento responde 405 (plan §4.1).

Las respuestas incluyen el pago acordado porque la lectura es con `staff:manage`
(decisión del PO, 25/11/2026). El router no aplica reglas de negocio: valida la
inmutabilidad de `worker_id`/`event_id` en la edición y delega en los casos de uso.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from local_eventos.modules.commercial.public_api import EventLookup
from local_eventos.modules.staff.application.errors import AssignmentImmutableError
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentView,
)
from local_eventos.modules.staff.presentation.assignment_schemas import (
    AssignmentCancel,
    AssignmentCreate,
    AssignmentListOut,
    AssignmentOut,
    AssignmentProblem,
    AssignmentUpdate,
)
from local_eventos.modules.staff.presentation.dependencies import (
    AssignmentGetter,
    Canceller,
    Events,
    Lister,
    Registrar,
    StaffAssign,
    StaffManager,
    Updater,
)
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/staff/assignments",
    tags=["staff"],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

_Responses = dict[int | str, dict[str, Any]]

_NOT_FOUND: _Responses = {
    404: {
        "model": Problem,
        "description": "`staff.assignment_not_found`, `staff.event_not_found`, `staff.not_found`",
    }
}
_CONFLICT: _Responses = {
    409: {
        "model": AssignmentProblem,
        "description": (
            "`staff.worker_inactive`, `staff.event_not_assignable`, "
            "`staff.assignment_overlap` (con `conflicts`), `staff.assignment_immutable`, "
            "`staff.worker_has_future_assignments`"
        ),
    }
}
_INVALID: _Responses = {
    422: {
        "model": Problem,
        "description": (
            "Validación: `staff.assignment_schedule_invalid`, `staff.assignment_date_invalid`, "
            "`staff.assignment_function_required`, `staff.assignment_pay_invalid`, "
            "`staff.assignment_reason_required`, etc."
        ),
    }
}

_EVENT_ID = Annotated[UUID, Query(description="Evento cuyas asignaciones vigentes se listan")]


async def _with_event(view: AssignmentView, events: EventLookup) -> AssignmentView:
    """Completa código y estado del evento que el repositorio no puede consultar (regla 3)."""
    if view.event_code is not None and view.event_status is not None:
        return view
    event = await events(view.event_id)
    if event is None:
        return view
    return replace(view, event_code=event.code, event_status=event.status)


async def _enriched(
    assignment_id: UUID, getter: AssignmentGetter, events: EventLookup
) -> AssignmentView:
    """Lee la vista persistida y la completa con el evento para devolver `AssignmentOut`."""
    view = await getter.execute(assignment_id)
    return await _with_event(view, events)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    operation_id="staff_assignment_register",
    response_model=AssignmentOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
)
async def register_assignment(
    body: AssignmentCreate,
    registrar: Registrar,
    getter: AssignmentGetter,
    events: Events,
    user: StaffAssign,
) -> AssignmentOut:
    """Crea una asignación activa y devuelve la vista con el evento y el trabajador."""
    assignment = await registrar.execute(
        event_id=body.event_id,
        worker_id=body.worker_id,
        function=body.function,
        function_description=body.function_description,
        date=body.date,
        start_time=body.start_time,
        end_time=body.end_time,
        pay_cents=body.pay_cents,
        actor_id=user.id,
    )
    view = await _enriched(assignment.id, getter, events)
    return AssignmentOut.from_view(view)


@router.get(
    "",
    operation_id="staff_assignment_list",
    response_model=AssignmentListOut,
    responses={**_NOT_FOUND},
)
async def list_event_assignments(
    event_id: _EVENT_ID,
    lister: Lister,
    _user: StaffManager,
) -> AssignmentListOut:
    """Lista las asignaciones vigentes de un evento, ordenadas por hora de inicio."""
    views = await lister.execute(event_id)
    return AssignmentListOut(items=[AssignmentOut.from_view(view) for view in views])


@router.get(
    "/{assignment_id}",
    operation_id="staff_assignment_get",
    response_model=AssignmentOut,
    responses={**_NOT_FOUND},
)
async def get_assignment(
    assignment_id: UUID,
    getter: AssignmentGetter,
    events: Events,
    _user: StaffManager,
) -> AssignmentOut:
    """Detalle de una asignación, activa o anulada."""
    view = await _enriched(assignment_id, getter, events)
    return AssignmentOut.from_view(view)


@router.put(
    "/{assignment_id}",
    operation_id="staff_assignment_update",
    response_model=AssignmentOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
)
async def update_assignment(
    assignment_id: UUID,
    body: AssignmentUpdate,
    updater: Updater,
    getter: AssignmentGetter,
    events: Events,
    user: StaffAssign,
) -> AssignmentOut:
    """Reemplazo completo de los campos editables; el motivo es obligatorio."""
    if body.worker_id is not None or body.event_id is not None:
        raise AssignmentImmutableError()
    assignment = await updater.execute(
        assignment_id=assignment_id,
        function=body.function,
        function_description=body.function_description,
        date=body.date,
        start_time=body.start_time,
        end_time=body.end_time,
        pay_cents=body.pay_cents,
        reason=body.reason,
        actor_id=user.id,
    )
    view = await _enriched(assignment.id, getter, events)
    return AssignmentOut.from_view(view)


@router.post(
    "/{assignment_id}/cancel",
    operation_id="staff_assignment_cancel",
    response_model=AssignmentOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
)
async def cancel_assignment(
    assignment_id: UUID,
    body: AssignmentCancel,
    canceller: Canceller,
    getter: AssignmentGetter,
    events: Events,
    user: StaffAssign,
) -> AssignmentOut:
    """Anulación lógica con motivo; repetir la operación es idempotente."""
    assignment = await canceller.execute(
        assignment_id=assignment_id,
        reason=body.reason,
        actor_id=user.id,
    )
    view = await _enriched(assignment.id, getter, events)
    return AssignmentOut.from_view(view)


__all__ = ["router"]
