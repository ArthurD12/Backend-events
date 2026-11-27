"""Ensamblaje de dependencias del módulo staff.

Es el único lugar que conoce las clases concretas de `infrastructure`: el resto del
módulo trabaja con los puertos (`WorkerRepository`, `AssignmentRepository`, `Clock`).
Construye los repositorios sobre la sesión de la petición, el reloj del sistema y los
casos de uso: personal (`RegisterWorker`, `UpdateWorker`, `GetWorker`,
`SearchWorkers`, `DeactivateWorker`, `ActivateWorker`) y asignaciones HU17
(`RegisterAssignment`, `UpdateAssignment`, `CancelAssignment`,
`ListEventAssignments`, `GetAssignment`). La presentación solo adapta HTTP y delega
aquí. El evento se obtiene por `commercial.public_api.event_lookup` y la ocupación
(`AssignmentOccupancy`) libera los eventos cancelados de forma perezosa.

HU16 añade los repositorios de indisponibilidades y la lectura de la función de las
asignaciones en conflicto, ambos de solo lectura salvo `save` de indisponibilidad.

`worker_lookup` y `event_assignments` son las fábricas de los puertos públicos que
usarán otros módulos: la primera expone estado y función del trabajador; la segunda,
las asignaciones de un evento **sin pago** para la ficha consolidada (HU14).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial.public_api import event_lookup
from local_eventos.modules.staff.application.assignment_occupancy import AssignmentOccupancy
from local_eventos.modules.staff.application.ports.assignment_conflict_lookup import (
    AssignmentConflictLookup,
)
from local_eventos.modules.staff.application.ports.assignment_repository import (
    EventAssignment,
    EventAssignmentLookup,
)
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.unavailability_repository import (
    UnavailabilityRepository,
)
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerLookup,
    WorkerRef,
    WorkerRepository,
)
from local_eventos.modules.staff.application.use_cases.cancel_assignment import (
    CancelAssignment,
)
from local_eventos.modules.staff.application.use_cases.change_worker_status import (
    ActivateWorker,
    DeactivateWorker,
)
from local_eventos.modules.staff.application.use_cases.get_assignment import GetAssignment
from local_eventos.modules.staff.application.use_cases.get_worker import GetWorker
from local_eventos.modules.staff.application.use_cases.get_worker_ref import GetWorkerRef
from local_eventos.modules.staff.application.use_cases.list_event_assignments import (
    ListEventAssignments,
)
from local_eventos.modules.staff.application.use_cases.list_event_assignments_for_sheet import (
    ListEventAssignmentsForSheet,
)
from local_eventos.modules.staff.application.use_cases.register_assignment import (
    RegisterAssignment,
)
from local_eventos.modules.staff.application.use_cases.register_worker import (
    RegisterWorker,
)
from local_eventos.modules.staff.application.use_cases.search_workers import (
    SearchWorkers,
)
from local_eventos.modules.staff.application.use_cases.update_assignment import (
    UpdateAssignment,
)
from local_eventos.modules.staff.application.use_cases.update_worker import (
    UpdateWorker,
)
from local_eventos.modules.staff.infrastructure.assignment_conflict_lookup import (
    SqlAlchemyAssignmentConflictLookup,
)
from local_eventos.modules.staff.infrastructure.assignment_repository import (
    SqlAlchemyAssignmentRepository,
)
from local_eventos.modules.staff.infrastructure.clock import SystemClock
from local_eventos.modules.staff.infrastructure.unavailability_repository import (
    SqlAlchemyUnavailabilityRepository,
)
from local_eventos.modules.staff.infrastructure.worker_repository import (
    SqlAlchemyWorkerRepository,
)


def worker_repository(session: AsyncSession) -> WorkerRepository:
    """Repositorio sobre la sesión transaccional de la petición."""
    return SqlAlchemyWorkerRepository(session)


def assignment_repository(session: AsyncSession) -> SqlAlchemyAssignmentRepository:
    """Repositorio de asignaciones sobre la sesión de la petición (HU17)."""
    return SqlAlchemyAssignmentRepository(session)


def assignment_occupancy(session: AsyncSession) -> AssignmentOccupancy:
    """Ocupación del trabajador: libera eventos cancelados y detecta futuras."""
    return AssignmentOccupancy(assignment_repository(session), event_lookup(session))


def unavailabilities(session: AsyncSession) -> UnavailabilityRepository:
    """Repositorio de indisponibilidades sobre la sesión de la petición (HU16)."""
    return SqlAlchemyUnavailabilityRepository(session)


def assignment_conflicts(session: AsyncSession) -> AssignmentConflictLookup:
    """Lectura de la función de asignaciones por id, sin pago ni solape (HU16)."""
    return SqlAlchemyAssignmentConflictLookup(session)


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
    return DeactivateWorker(worker_repository(session), clock(), assignment_occupancy(session))


def activate_worker(session: AsyncSession) -> ActivateWorker:
    return ActivateWorker(worker_repository(session), clock())


def register_assignment(session: AsyncSession) -> RegisterAssignment:
    """Alta de asignación con repositorio, trabajadores, eventos, ocupación y reloj (HU17)."""
    assignments = assignment_repository(session)
    events = event_lookup(session)
    return RegisterAssignment(
        assignments,
        worker_lookup(session),
        events,
        AssignmentOccupancy(assignments, events),
        clock(),
    )


def update_assignment(session: AsyncSession) -> UpdateAssignment:
    """Edición de asignación con el mismo cableado que el alta (HU17)."""
    assignments = assignment_repository(session)
    events = event_lookup(session)
    return UpdateAssignment(
        assignments,
        worker_lookup(session),
        events,
        AssignmentOccupancy(assignments, events),
        clock(),
    )


def cancel_assignment(session: AsyncSession) -> CancelAssignment:
    """Anulación lógica de una asignación (HU17)."""
    return CancelAssignment(assignment_repository(session), event_lookup(session), clock())


def list_event_assignments(session: AsyncSession) -> ListEventAssignments:
    """Listado de asignaciones vigentes de un evento (HU17)."""
    return ListEventAssignments(assignment_repository(session), event_lookup(session))


def get_assignment(session: AsyncSession) -> GetAssignment:
    """Detalle de una asignación, incluidas las anuladas (HU17)."""
    return GetAssignment(assignment_repository(session))


def worker_lookup(session: AsyncSession) -> WorkerLookup:
    """Consulta mínima del personal para otros módulos (solo lectura)."""
    return _WorkerLookup(GetWorkerRef(worker_repository(session)))


def event_assignments(session: AsyncSession) -> EventAssignmentLookup:
    """Consulta pública de las asignaciones de un evento para HU14 (sin pago).

    Devuelve nombre, función, descripción e instantes UTC; nunca pago, documento,
    teléfono ni tarifa. `reporting` la usa en lugar de su adaptador nulo.
    """
    return _EventAssignments(ListEventAssignmentsForSheet(assignment_repository(session)))


class _WorkerLookup:
    """Adaptador del caso de uso `GetWorkerRef` al puerto `WorkerLookup`."""

    def __init__(self, use_case: GetWorkerRef) -> None:
        self._use_case = use_case

    async def get(self, worker_id: UUID) -> WorkerRef | None:
        return await self._use_case.execute(worker_id)


class _EventAssignments:
    """Adaptador de `ListEventAssignmentsForSheet` al puerto `EventAssignmentLookup`."""

    def __init__(self, use_case: ListEventAssignmentsForSheet) -> None:
        self._use_case = use_case

    async def __call__(self, event_id: UUID) -> list[EventAssignment]:
        return await self._use_case.execute(event_id)


__all__ = [
    "WorkerLookup",
    "activate_worker",
    "assignment_conflicts",
    "assignment_occupancy",
    "assignment_repository",
    "cancel_assignment",
    "clock",
    "deactivate_worker",
    "event_assignments",
    "get_assignment",
    "get_worker",
    "list_event_assignments",
    "register_assignment",
    "register_worker",
    "search_workers",
    "unavailabilities",
    "update_assignment",
    "update_worker",
    "worker_lookup",
    "worker_repository",
]
