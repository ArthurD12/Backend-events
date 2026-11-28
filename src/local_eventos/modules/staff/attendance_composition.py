"""Ensamblaje de dependencias de la asistencia del personal (HU18, T-09, plan §3).

Es el único lugar de la feature que conoce las clases concretas de
`infrastructure`: la presentación solo adapta HTTP y delega aquí. Construye el
repositorio de asistencia sobre la sesión de la petición, el reloj del sistema
(UTC), y los casos de uso `UpdateAttendance` y `GetAttendanceHistory` con los
puertos existentes (`WorkerLookup` de HU15 y `EventLookup` de
`commercial.public_api`). El evento se resuelve de forma tolerante: un evento
huérfano deja los campos en `null` (R-ATT-23).

`user_names` expone la fábrica de `identity.public_api`: la presentación la usa
para resolver el nombre del actor que registró la asistencia, solo de los actores
de la página. No se edita `composition.py` de HU16/HU17.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial.public_api import event_lookup
from local_eventos.modules.identity.public_api import UserNamesLookup
from local_eventos.modules.identity.public_api import user_names as identity_user_names
from local_eventos.modules.staff.application.ports.attendance_repository import (
    AttendanceRepository,
)
from local_eventos.modules.staff.application.use_cases.get_attendance_history import (
    GetAttendanceHistory,
)
from local_eventos.modules.staff.application.use_cases.update_attendance import (
    UpdateAttendance,
)
from local_eventos.modules.staff.composition import clock, worker_lookup
from local_eventos.modules.staff.infrastructure.attendance_repository import (
    SqlAlchemyAttendanceRepository,
)

__all__ = [
    "attendance_history",
    "attendance_repository",
    "clock",
    "update_attendance",
    "user_names",
]


def attendance_repository(session: AsyncSession) -> AttendanceRepository:
    """Repositorio de asistencia sobre la sesión transaccional de la petición."""
    return SqlAlchemyAttendanceRepository(session)


def update_attendance(session: AsyncSession) -> UpdateAttendance:
    """Registro/corrección con repositorio, eventos tolerantes y reloj UTC."""
    return UpdateAttendance(attendance_repository(session), event_lookup(session), clock())


def attendance_history(session: AsyncSession) -> GetAttendanceHistory:
    """Historial por trabajador con `WorkerLookup` y eventos tolerantes."""
    return GetAttendanceHistory(
        attendance_repository(session),
        worker_lookup(session),
        event_lookup(session),
    )


def user_names(session: AsyncSession) -> UserNamesLookup:
    """Nombres de usuario de `identity.public_api` para la presentación."""
    return identity_user_names(session)
