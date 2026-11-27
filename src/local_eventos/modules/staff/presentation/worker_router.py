"""Endpoints de trabajadores (HU15). Traducen HTTP ⇄ casos de uso; sin reglas de negocio.

Todas las rutas exigen el permiso `staff:manage` (administrador y encargado de
eventos; compras no tiene acceso, ni siquiera lectura). No existe `DELETE`: la baja
es lógica mediante `deactivate` y la fila se conserva (plan §5.1, CA-15.11).
`PUT` es reemplazo completo de los campos editables.
"""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from local_eventos.modules.staff.application.use_cases.change_worker_status import (
    ActivateWorker,
    DeactivateWorker,
)
from local_eventos.modules.staff.application.use_cases.get_worker import GetWorker
from local_eventos.modules.staff.application.use_cases.register_worker import (
    RegisterWorker,
)
from local_eventos.modules.staff.application.use_cases.search_workers import (
    DEFAULT_PAGE_SIZE,
    SearchWorkers,
)
from local_eventos.modules.staff.application.use_cases.update_worker import (
    UpdateWorker,
)
from local_eventos.modules.staff.application.use_cases.worker_data import WorkerData
from local_eventos.modules.staff.domain.enums import WorkerFunction
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.presentation.dependencies import (
    Now,
    Occupancy,
    StaffManager,
    Workers,
    require_staff_manage,
)
from local_eventos.modules.staff.presentation.worker_schemas import (
    WorkerCreate,
    WorkerOut,
    WorkerPageOut,
    WorkerUpdate,
)
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/staff",
    tags=["personal"],
    dependencies=[Depends(require_staff_manage)],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

_Responses = dict[int | str, dict[str, Any]]

_NOT_FOUND: _Responses = {404: {"model": Problem, "description": "`staff.not_found`"}}
_DUPLICATED: _Responses = {409: {"model": Problem, "description": "`staff.document_duplicated`"}}
_INVALID: _Responses = {
    422: {"model": Problem, "description": "Dato inválido: `staff.name_required`, etc."}
}

_StatusFilter = Literal["ACTIVE", "INACTIVE", "ALL"]


class WorkerStatusChange(BaseModel):
    """Cuerpo opcional de baja y reactivación: motivo libre, no obligatorio."""

    reason: str | None = Field(default=None, description="Motivo de la baja o reactivación")


def _to_data(body: WorkerCreate | WorkerUpdate) -> WorkerData:
    """Mapea el esquema de la API al DTO de aplicación, con importes en céntimos."""
    return WorkerData(
        name=body.name,
        document_type=body.document_type,
        document_number=body.document_number,
        phone=body.phone,
        function=body.function,
        function_description=body.function_description,
        worker_type=body.worker_type,
        rate=None if body.rate_cents is None else Money(body.rate_cents),
        overtime_applies=body.overtime_applies,
        overtime_rate=(
            None if body.overtime_rate_cents is None else Money(body.overtime_rate_cents)
        ),
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    operation_id="staff_register",
    responses={**_DUPLICATED, **_INVALID},
)
async def register_worker(
    body: WorkerCreate,
    workers: Workers,
    clock: Now,
    user: StaffManager,
) -> WorkerOut:
    """Registra un trabajador nuevo, siempre activo. El documento no puede repetirse."""
    worker = await RegisterWorker(workers, clock).execute(_to_data(body), user.id)
    return WorkerOut.from_worker(worker)


@router.get("", operation_id="staff_search")
async def search_workers(
    workers: Workers,
    function: WorkerFunction | None = None,
    status_filter: Annotated[
        _StatusFilter, Query(alias="status", description="ACTIVE por defecto; ALL incluye ambos")
    ] = "ACTIVE",
    text: Annotated[str, Query(description="Parte del nombre o del documento")] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = DEFAULT_PAGE_SIZE,
) -> WorkerPageOut:
    """Lista trabajadores por función y estado, con búsqueda por nombre o documento."""
    found = await SearchWorkers(workers).execute(
        text=text,
        function=function,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return WorkerPageOut.from_page(found)


@router.get("/{worker_id}", operation_id="staff_get", responses=_NOT_FOUND)
async def get_worker(worker_id: UUID, workers: Workers) -> WorkerOut:
    """Ficha completa de un trabajador, activo o inactivo (la baja es lógica)."""
    return WorkerOut.from_worker(await GetWorker(workers).execute(worker_id))


@router.put(
    "/{worker_id}",
    operation_id="staff_update",
    responses={**_NOT_FOUND, **_DUPLICATED, **_INVALID},
)
async def update_worker(
    worker_id: UUID,
    body: WorkerUpdate,
    workers: Workers,
    clock: Now,
    user: StaffManager,
) -> WorkerOut:
    """Reemplazo completo de los datos editables: si un opcional se omite, se limpia."""
    worker = await UpdateWorker(workers, clock).execute(worker_id, _to_data(body), user.id)
    return WorkerOut.from_worker(worker)


@router.post("/{worker_id}/deactivate", operation_id="staff_deactivate", responses=_NOT_FOUND)
async def deactivate_worker(
    worker_id: UUID,
    workers: Workers,
    clock: Now,
    occupancy: Occupancy,
    user: StaffManager,
    body: WorkerStatusChange | None = None,
) -> WorkerOut:
    """Baja lógica con motivo opcional. Repetir la operación no audita otra vez."""
    reason = None if body is None else body.reason
    worker = await DeactivateWorker(workers, clock, occupancy).execute(worker_id, reason, user.id)
    return WorkerOut.from_worker(worker)


@router.post("/{worker_id}/activate", operation_id="staff_activate", responses=_NOT_FOUND)
async def activate_worker(
    worker_id: UUID,
    workers: Workers,
    clock: Now,
    user: StaffManager,
    body: WorkerStatusChange | None = None,
) -> WorkerOut:
    """Reactiva a un trabajador dado de baja, con motivo opcional."""
    reason = None if body is None else body.reason
    worker = await ActivateWorker(workers, clock).execute(worker_id, reason, user.id)
    return WorkerOut.from_worker(worker)
