"""Dependencias de FastAPI del módulo staff: repositorio, reloj y usuario actual.

La fábrica del repositorio vive aquí de forma provisional: `composition.py` (T-17)
la centralizará. En las pruebas se reemplaza `get_worker_repository` por un
repositorio en memoria y `get_current_user` por un usuario ya autenticado.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.identity.public_api import (
    CurrentUser,
    Permission,
    require_permission,
)
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerRepository,
)
from local_eventos.modules.staff.infrastructure.clock import SystemClock
from local_eventos.modules.staff.infrastructure.worker_repository import (
    SqlAlchemyWorkerRepository,
)
from local_eventos.shared.presentation.database import get_session

__all__ = [
    "Clock",
    "CurrentUser",
    "Now",
    "Permission",
    "StaffManager",
    "Workers",
    "get_clock",
    "get_worker_repository",
    "require_permission",
    "require_staff_manage",
]


async def get_worker_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkerRepository:
    """Construye el repositorio sobre la sesión transaccional de la petición."""
    return SqlAlchemyWorkerRepository(session)


Workers = Annotated[WorkerRepository, Depends(get_worker_repository)]


def get_clock() -> Clock:
    """Reloj del sistema: la fecha de auditoría se toma una vez por operación."""
    return SystemClock()


Now = Annotated[Clock, Depends(get_clock)]

require_staff_manage = require_permission(Permission.STAFF_MANAGE)

StaffManager = Annotated[CurrentUser, Depends(require_staff_manage)]
