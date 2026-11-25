"""Ensamblaje de dependencias del módulo staff.

Es el único lugar que conoce las clases concretas de `infrastructure`: el resto del
módulo trabaja con los puertos (`WorkerRepository`, `Clock`). Construye el
repositorio sobre la sesión de la petición, el reloj del sistema y los casos de uso
(`RegisterWorker`, `UpdateWorker`, `GetWorker`, `SearchWorkers`, `DeactivateWorker`,
`ActivateWorker`); la presentación solo adapta HTTP y delega aquí.

`worker_lookup` es la fábrica del puerto público que usarán otros módulos (por
ejemplo HU17) para consultar estado y función sin acceder a datos sensibles.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerLookup,
    WorkerRef,
    WorkerRepository,
)
from local_eventos.modules.staff.application.use_cases.change_worker_status import (
    ActivateWorker,
    DeactivateWorker,
)
from local_eventos.modules.staff.application.use_cases.get_worker import GetWorker
from local_eventos.modules.staff.application.use_cases.get_worker_ref import GetWorkerRef
from local_eventos.modules.staff.application.use_cases.register_worker import (
    RegisterWorker,
)
from local_eventos.modules.staff.application.use_cases.search_workers import (
    SearchWorkers,
)
from local_eventos.modules.staff.application.use_cases.update_worker import (
    UpdateWorker,
)
from local_eventos.modules.staff.infrastructure.clock import SystemClock
from local_eventos.modules.staff.infrastructure.worker_repository import (
    SqlAlchemyWorkerRepository,
)


def worker_repository(session: AsyncSession) -> WorkerRepository:
    """Repositorio sobre la sesión transaccional de la petición."""
    return SqlAlchemyWorkerRepository(session)


def clock() -> Clock:
    """Reloj del sistema: la fecha de auditoría se toma una vez por operación."""
    return SystemClock()


def register_worker(session: AsyncSession) -> RegisterWorker:
    return RegisterWorker(worker_repository(session), clock())


def update_worker(session: AsyncSession) -> UpdateWorker:
    return UpdateWorker(worker_repository(session), clock())


def get_worker(session: AsyncSession) -> GetWorker:
    return GetWorker(worker_repository(session))


def search_workers(session: AsyncSession) -> SearchWorkers:
    return SearchWorkers(worker_repository(session))


def deactivate_worker(session: AsyncSession) -> DeactivateWorker:
    return DeactivateWorker(worker_repository(session), clock())


def activate_worker(session: AsyncSession) -> ActivateWorker:
    return ActivateWorker(worker_repository(session), clock())


def worker_lookup(session: AsyncSession) -> WorkerLookup:
    """Consulta mínima del personal para otros módulos (solo lectura)."""
    return _WorkerLookup(GetWorkerRef(worker_repository(session)))


class _WorkerLookup:
    """Adaptador del caso de uso `GetWorkerRef` al puerto `WorkerLookup`."""

    def __init__(self, use_case: GetWorkerRef) -> None:
        self._use_case = use_case

    async def get(self, worker_id: UUID) -> WorkerRef | None:
        return await self._use_case.execute(worker_id)


__all__ = [
    "WorkerLookup",
    "activate_worker",
    "clock",
    "deactivate_worker",
    "get_worker",
    "register_worker",
    "search_workers",
    "update_worker",
    "worker_lookup",
    "worker_repository",
]
