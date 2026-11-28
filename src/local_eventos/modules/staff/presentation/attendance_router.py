"""Endpoints de asistencia del personal (HU18). Traducen HTTP ⇄ casos de uso.

Dos rutas bajo `/v1/staff`:

- `PATCH /assignments/{assignment_id}/attendance` (registrar/corregir) exige
  `staff:attendance`, solo administrador (R-ATT-14/CA-18.9).
- `GET /workers/{worker_id}/attendance` (historial, con pago) exige
  `staff:manage`, solo administrador. `staff_roster:read` no abre ninguna.

No existe `DELETE`: la asistencia se corrige con `PATCH`. El router no aplica
reglas de negocio; delega en `UpdateAttendance`/`GetAttendanceHistory` y solo
resuelve los nombres de los actores de la página con `identity.public_api`
(una llamada por página). Un evento huérfano se serializa con sus campos en
`null`, nunca como 404 (R-ATT-23).

**Orden de registro**: este router va en `main.py` después de asignaciones y
antes de disponibilidad/trabajadores (plan §4.5).
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query

from local_eventos.modules.staff.presentation.attendance_dependencies import (
    AttendanceGetter,
    AttendanceUpdater,
    StaffAttendance,
    StaffManager,
    UserNames,
)
from local_eventos.modules.staff.presentation.attendance_schemas import (
    AttendanceHistoryPage,
    AttendanceOut,
    AttendanceUpdate,
)
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/staff",
    tags=["staff"],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

_Responses = dict[int | str, dict[str, Any]]

_PATCH_NOT_FOUND: _Responses = {
    404: {
        "model": Problem,
        "description": "`staff.assignment_not_found`",
    }
}
_PATCH_CONFLICT: _Responses = {
    409: {
        "model": Problem,
        "description": "`staff.attendance_not_due`, `staff.attendance_assignment_cancelled`",
    }
}
_PATCH_INVALID: _Responses = {
    422: {
        "model": Problem,
        "description": (
            "Validación: `staff.attendance_status_invalid`, `staff.attendance_reason_required`"
        ),
    }
}
_GET_NOT_FOUND: _Responses = {
    404: {
        "model": Problem,
        "description": "`staff.worker_not_found`",
    }
}
_GET_INVALID: _Responses = {
    422: {
        "model": Problem,
        "description": (
            "Validación: `staff.attendance_date_range_invalid` (rango de fechas o paginación)"
        ),
    }
}

_FROM = Annotated[
    date_type | None,
    Query(alias="from", description="Fecha mínima del evento (America/Lima), inclusiva"),
]
_TO = Annotated[
    date_type | None,
    Query(alias="to", description="Fecha máxima del evento (America/Lima), inclusiva"),
]
_EVENT_ID = Annotated[UUID | None, Query(description="Solo asignaciones de ese evento")]
_PAGE = Annotated[int, Query(description="Número de página, desde 1")]
_PAGE_SIZE = Annotated[int, Query(description="Tamaño de página, 1..100")]


@router.patch(
    "/assignments/{assignment_id}/attendance",
    operation_id="staff_attendance_update",
    response_model=AttendanceOut,
    responses={**_PATCH_NOT_FOUND, **_PATCH_CONFLICT, **_PATCH_INVALID},
)
async def update_attendance(
    assignment_id: UUID,
    body: AttendanceUpdate,
    updater: AttendanceUpdater,
    user_names: UserNames,
    user: StaffAttendance,
) -> AttendanceOut:
    """Registra el primer estado o corrige el vigente, auditando la corrección."""
    result = await updater.execute(
        assignment_id=assignment_id,
        status=body.status,
        reason=body.reason,
        actor_id=user.id,
    )
    actor = result.attendance.recorded_by
    names = await user_names([actor])
    return AttendanceOut.from_parts(
        assignment=result.assignment,
        attendance_status=result.attendance.status,
        recorded_at=result.attendance.recorded_at,
        recorded_by=actor,
        recorded_by_name=names.get(actor),
        event=result.event,
    )


@router.get(
    "/workers/{worker_id}/attendance",
    operation_id="staff_attendance_history",
    response_model=AttendanceHistoryPage,
    responses={**_GET_NOT_FOUND, **_GET_INVALID},
)
async def get_attendance_history(
    worker_id: UUID,
    getter: AttendanceGetter,
    user_names: UserNames,
    _user: StaffManager,
    from_: _FROM = None,
    to_: _TO = None,
    event_id: _EVENT_ID = None,
    page: _PAGE = 1,
    page_size: _PAGE_SIZE = 20,
) -> AttendanceHistoryPage:
    """Historial del trabajador, incluidos anulados, con eventos anulables."""
    page_result = await getter.execute(
        worker_id=worker_id,
        from_=from_,
        to_=to_,
        event_id=event_id,
        page=page,
        page_size=page_size,
    )
    actor_ids: set[UUID] = {
        item.row.recorded_by for item in page_result.items if item.row.recorded_by is not None
    }
    names = await user_names(actor_ids) if actor_ids else {}
    return AttendanceHistoryPage(
        items=[
            AttendanceOut.from_parts(
                assignment=item.row,
                attendance_status=item.row.attendance_status,
                recorded_at=item.row.recorded_at,
                recorded_by=item.row.recorded_by,
                recorded_by_name=(
                    names.get(item.row.recorded_by) if item.row.recorded_by is not None else None
                ),
                event=item.event,
            )
            for item in page_result.items
        ],
        total=page_result.total,
        page=page_result.page,
        page_size=page_result.page_size,
    )


__all__ = ["router"]
