"""Adaptador HTTP del módulo staff: dependencias de FastAPI.

La construcción de repositorio y reloj vive en `staff.composition`; aquí solo se
envuelve en `Depends` y se resuelve el usuario actual. En las pruebas se reemplaza
`get_worker_repository` por un repositorio en memoria y `get_current_user` por un
usuario ya autenticado.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial.public_api import EventLookup, event_lookup
from local_eventos.modules.identity.public_api import (
    CurrentUser,
    Permission,
    require_permission,
)
from local_eventos.modules.staff import composition
from local_eventos.modules.staff.application.assignment_occupancy import AssignmentOccupancy
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentRepository,
)
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerLookup,
    WorkerRepository,
)
from local_eventos.modules.staff.application.use_cases.cancel_assignment import (
    CancelAssignment,
)
from local_eventos.modules.staff.application.use_cases.get_assignment import GetAssignment
from local_eventos.modules.staff.application.use_cases.list_event_assignments import (
    ListEventAssignments,
)
from local_eventos.modules.staff.application.use_cases.register_assignment import (
    RegisterAssignment,
)
from local_eventos.modules.staff.application.use_cases.update_assignment import (
    UpdateAssignment,
)
from local_eventos.shared.presentation.database import get_session

__all__ = [
    "AssignmentGetter",
    "AssignmentRepository",
    "Assignments",
    "Canceller",
    "Clock",
    "CurrentUser",
    "EventLookup",
    "Events",
    "Lister",
    "Now",
    "Occupancy",
    "Permission",
    "Registrar",
    "StaffAssign",
    "StaffManager",
    "Updater",
    "Workers",
    "WorkersLookup",
    "get_assignment_occupancy",
    "get_assignment_repository",
    "get_assignment_use_case",
    "get_cancel_assignment",
    "get_clock",
    "get_event_lookup",
    "get_list_event_assignments",
    "get_register_assignment",
    "get_update_assignment",
    "get_worker_lookup",
    "get_worker_repository",
    "require_permission",
    "require_staff_assign",
    "require_staff_manage",
]


async def get_worker_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkerRepository:
    """Construye el repositorio sobre la sesión transaccional de la petición."""
    return composition.worker_repository(session)


Workers = Annotated[WorkerRepository, Depends(get_worker_repository)]


async def get_assignment_occupancy(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AssignmentOccupancy:
    """Ocupación del trabajador sobre la sesión de la petición (HU17)."""
    return composition.assignment_occupancy(session)


Occupancy = Annotated[AssignmentOccupancy, Depends(get_assignment_occupancy)]


def get_clock() -> Clock:
    """Reloj del sistema: la fecha de auditoría se toma una vez por operación."""
    return composition.clock()


Now = Annotated[Clock, Depends(get_clock)]

require_staff_manage = require_permission(Permission.STAFF_MANAGE)

StaffManager = Annotated[CurrentUser, Depends(require_staff_manage)]

require_staff_assign = require_permission(Permission.STAFF_ASSIGN)

StaffAssign = Annotated[CurrentUser, Depends(require_staff_assign)]


async def get_assignment_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AssignmentRepository:
    """Repositorio de asignaciones sobre la sesión de la petición (HU17)."""
    return composition.assignment_repository(session)


Assignments = Annotated[AssignmentRepository, Depends(get_assignment_repository)]


async def get_worker_lookup(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkerLookup:
    """Consulta mínima del personal para validar asignaciones (HU17)."""
    return composition.worker_lookup(session)


WorkersLookup = Annotated[WorkerLookup, Depends(get_worker_lookup)]


async def get_event_lookup(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventLookup:
    """Consulta de solo lectura de eventos por `commercial.public_api` (HU17)."""
    return event_lookup(session)


Events = Annotated[EventLookup, Depends(get_event_lookup)]


async def get_register_assignment(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegisterAssignment:
    """Caso de uso de alta de asignación (HU17)."""
    return composition.register_assignment(session)


Registrar = Annotated[RegisterAssignment, Depends(get_register_assignment)]


async def get_update_assignment(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UpdateAssignment:
    """Caso de uso de edición de asignación (HU17)."""
    return composition.update_assignment(session)


Updater = Annotated[UpdateAssignment, Depends(get_update_assignment)]


async def get_cancel_assignment(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CancelAssignment:
    """Caso de uso de anulación de asignación (HU17)."""
    return composition.cancel_assignment(session)


Canceller = Annotated[CancelAssignment, Depends(get_cancel_assignment)]


async def get_list_event_assignments(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ListEventAssignments:
    """Caso de uso de listado de asignaciones de un evento (HU17)."""
    return composition.list_event_assignments(session)


Lister = Annotated[ListEventAssignments, Depends(get_list_event_assignments)]


async def get_assignment_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GetAssignment:
    """Caso de uso de detalle de una asignación (HU17)."""
    return composition.get_assignment(session)


AssignmentGetter = Annotated[GetAssignment, Depends(get_assignment_use_case)]
