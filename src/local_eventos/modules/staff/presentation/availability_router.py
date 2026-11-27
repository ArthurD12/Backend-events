"""Endpoints de disponibilidad del personal (HU16). Traducen HTTP ⇄ casos de uso.

Cinco rutas bajo `/v1/staff`, todas con el permiso `staff:availability` (solo
administrador): consulta de disponibilidad, listado, alta, edición y anulación
lógica de indisponibilidades. No existe `DELETE`; un intento responde 405 y la
anulación es `POST .../cancel` (plan §4.2).

**Orden de registro permanente**: las rutas literales `/availability` y
`/unavailability...` deben registrarse en `main.py` antes de
`GET /v1/staff/{worker_id}` (UUID); de lo contrario el path param captura las
rutas y devuelve 422 (plan §4.1).

El router no aplica reglas de negocio: convierte fecha/hora locales de Lima al
VO `AvailabilityQuery`, delega en los casos de uso y mapea los agregados a los
esquemas. La consulta y el listado son de solo lectura. No se publican metadatos
técnicos `created_at`/`updated_at`: el agregado no los tiene y la auditoría es la
fuente real de quién y cuándo.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import time
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from local_eventos.modules.staff.application.use_cases.get_staff_availability import (
    AvailabilityReport,
)
from local_eventos.modules.staff.domain.availability_query import AvailabilityQuery
from local_eventos.modules.staff.domain.enums import AvailabilityState, WorkerFunction
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.presentation.availability_schemas import (
    AvailabilityOut,
    UnavailabilityCancel,
    UnavailabilityCreate,
    UnavailabilityListOut,
    UnavailabilityOut,
    UnavailabilityUpdate,
)
from local_eventos.modules.staff.presentation.dependencies import (
    AvailabilityGetter,
    AvailabilityLister,
    AvailabilityRegistrar,
    AvailabilityUpdater,
    StaffAvailability,
    UnavailabilityCanceller,
    require_staff_availability,
)
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/staff",
    tags=["staff"],
    dependencies=[Depends(require_staff_availability)],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

_Responses = dict[int | str, dict[str, Any]]

_NOT_FOUND: _Responses = {
    404: {
        "model": Problem,
        "description": "`staff.not_found`, `staff.unavailability_not_found`",
    }
}
_CONFLICT: _Responses = {
    409: {
        "model": Problem,
        "description": "`staff.worker_inactive`, `staff.unavailability_cancelled`",
    }
}
_INVALID: _Responses = {
    422: {
        "model": Problem,
        "description": (
            "Validación: `staff.availability_window_invalid`, "
            "`staff.availability_range_too_large`, `staff.unavailability_schedule_invalid`, "
            "`staff.unavailability_kind_required`, "
            "`staff.unavailability_description_required/not_allowed`, "
            "`staff.unavailability_reason_required`, etc."
        ),
    }
}


def _to_out(item: Unavailability) -> UnavailabilityOut:
    """Mapea el agregado a la respuesta sin metadatos técnicos."""
    return UnavailabilityOut.from_unavailability(item)


@router.get(
    "/availability",
    operation_id="staff_availability_get",
    response_model=AvailabilityOut,
    responses=_INVALID,
)
async def get_staff_availability(
    getter: AvailabilityGetter,
    _user: StaffAvailability,
    from_date: Annotated[date_type, Query(description="Primer día local (America/Lima)")],
    to_date: Annotated[date_type, Query(description="Último día local (America/Lima)")],
    start_time: Annotated[time | None, Query(description="Hora local de inicio")] = None,
    end_time: Annotated[time | None, Query(description="Hora local de fin")] = None,
    function: Annotated[WorkerFunction | None, Query(description="Filtro por función")] = None,
    state: Annotated[AvailabilityState | None, Query(description="Filtro por estado")] = None,
) -> AvailabilityOut:
    """Consulta de solo lectura la disponibilidad en una ventana de hasta 31 días."""
    query = AvailabilityQuery(
        from_date=from_date,
        to_date=to_date,
        start_time=start_time,
        end_time=end_time,
        function=function,
        state=state,
    )
    report: AvailabilityReport = await getter.execute(query)
    return AvailabilityOut.from_report(report)


@router.get(
    "/unavailability",
    operation_id="staff_unavailability_list",
    response_model=UnavailabilityListOut,
    responses=_INVALID,
)
async def list_unavailability(
    lister: AvailabilityLister,
    _user: StaffAvailability,
    worker_id: Annotated[UUID | None, Query(description="Filtro por trabajador")] = None,
    from_date: Annotated[date_type | None, Query(description="Primer día local")] = None,
    to_date: Annotated[date_type | None, Query(description="Último día local")] = None,
) -> UnavailabilityListOut:
    """Lista indisponibilidades, incluidas las anuladas, sin escribir nada."""
    items = await lister.execute(
        worker_id=worker_id,
        from_date=from_date,
        to_date=to_date,
    )
    return UnavailabilityListOut(items=[_to_out(item) for item in items])


@router.post(
    "/unavailability",
    status_code=status.HTTP_201_CREATED,
    operation_id="staff_unavailability_register",
    response_model=UnavailabilityOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
)
async def register_unavailability(
    body: UnavailabilityCreate,
    registrar: AvailabilityRegistrar,
    _user: StaffAvailability,
) -> UnavailabilityOut:
    """Registra una indisponibilidad activa y audita el alta con el usuario."""
    item = await registrar.execute(
        worker_id=body.worker_id,
        date=body.date,
        start_time=body.start_time,
        end_time=body.end_time,
        kind=body.kind,
        description=body.description,
        actor_id=_user.id,
    )
    return _to_out(item)


@router.put(
    "/unavailability/{unavailability_id}",
    operation_id="staff_unavailability_update",
    response_model=UnavailabilityOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
)
async def update_unavailability(
    unavailability_id: UUID,
    body: UnavailabilityUpdate,
    updater: AvailabilityUpdater,
    _user: StaffAvailability,
) -> UnavailabilityOut:
    """Reemplazo completo de los campos editables; el motivo es obligatorio."""
    item = await updater.execute(
        unavailability_id=unavailability_id,
        date=body.date,
        start_time=body.start_time,
        end_time=body.end_time,
        kind=body.kind,
        description=body.description,
        reason=body.reason,
        actor_id=_user.id,
    )
    return _to_out(item)


@router.post(
    "/unavailability/{unavailability_id}/cancel",
    operation_id="staff_unavailability_cancel",
    response_model=UnavailabilityOut,
    responses={**_NOT_FOUND, **_INVALID},
)
async def cancel_unavailability(
    unavailability_id: UUID,
    body: UnavailabilityCancel,
    canceller: UnavailabilityCanceller,
    _user: StaffAvailability,
) -> UnavailabilityOut:
    """Anulación lógica con motivo; repetir la operación es idempotente."""
    item = await canceller.execute(
        unavailability_id=unavailability_id,
        reason=body.reason,
        actor_id=_user.id,
    )
    return _to_out(item)


__all__ = ["router"]
