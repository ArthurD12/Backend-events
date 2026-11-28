"""Dependencias FastAPI de la asistencia del personal (HU18, T-09, plan §4.4).

Envuelve en `Depends` lo que construye `staff.attendance_composition` y resuelve
el usuario actual. En pruebas se reemplazan las fábricas de casos de uso o el
repositorio en memoria.

Permisos: `PATCH` exige `staff:attendance` (solo administrador) y `GET` exige
`staff:manage` (solo administrador). `staff_roster:read` no abre ninguna de las
dos rutas (R-ATT-14/CA-18.9/CA-18.10). 401/403 los resuelve `require_permission`.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.identity.public_api import (
    CurrentUser,
    Permission,
    UserNamesLookup,
    require_permission,
)
from local_eventos.modules.staff import attendance_composition
from local_eventos.modules.staff.application.ports.attendance_repository import (
    AttendanceRepository,
)
from local_eventos.modules.staff.application.use_cases.get_attendance_history import (
    GetAttendanceHistory,
)
from local_eventos.modules.staff.application.use_cases.update_attendance import (
    UpdateAttendance,
)
from local_eventos.modules.staff.presentation.dependencies import (
    StaffManager,
    require_staff_manage,
)
from local_eventos.shared.presentation.database import get_session

__all__ = [
    "AttendanceGetter",
    "AttendanceRepository",
    "AttendanceUpdater",
    "Attendances",
    "CurrentUser",
    "Permission",
    "StaffAttendance",
    "StaffManager",
    "UserNames",
    "get_attendance_history",
    "get_attendance_repository",
    "get_update_attendance",
    "get_user_names",
    "require_staff_attendance",
    "require_staff_manage",
]


async def get_attendance_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AttendanceRepository:
    """Repositorio de asistencia sobre la sesión transaccional de la petición."""
    return attendance_composition.attendance_repository(session)


Attendances = Annotated[AttendanceRepository, Depends(get_attendance_repository)]


async def get_update_attendance(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UpdateAttendance:
    """Caso de uso de registro/corrección de asistencia."""
    return attendance_composition.update_attendance(session)


AttendanceUpdater = Annotated[UpdateAttendance, Depends(get_update_attendance)]


async def get_attendance_history(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GetAttendanceHistory:
    """Caso de uso del historial de asistencia por trabajador."""
    return attendance_composition.attendance_history(session)


AttendanceGetter = Annotated[GetAttendanceHistory, Depends(get_attendance_history)]


async def get_user_names(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserNamesLookup:
    """Nombres de usuario de `identity.public_api` para resolver autores."""
    return attendance_composition.user_names(session)


UserNames = Annotated[UserNamesLookup, Depends(get_user_names)]

require_staff_attendance = require_permission(Permission.STAFF_ATTENDANCE)

StaffAttendance = Annotated[CurrentUser, Depends(require_staff_attendance)]
