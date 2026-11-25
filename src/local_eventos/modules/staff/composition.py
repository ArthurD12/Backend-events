"""Ensamblaje de dependencias del módulo staff.

Es el único lugar que conoce las clases concretas de `infrastructure`: el resto del módulo
trabaja con los puertos.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial.public_api import event_lookup as commercial_event_lookup
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentRepository,
)
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.event_lookup import EventLookup
from local_eventos.modules.staff.application.ports.unavailability_repository import (
    UnavailabilityRepository,
)
from local_eventos.modules.staff.application.ports.worker_repository import WorkerRepository
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
    return SqlAlchemyWorkerRepository(session)


def unavailability_repository(session: AsyncSession) -> UnavailabilityRepository:
    return SqlAlchemyUnavailabilityRepository(session)


def assignment_repository(session: AsyncSession) -> AssignmentRepository:
    return SqlAlchemyAssignmentRepository(session)


def clock() -> Clock:
    return SystemClock()


def event_lookup(session: AsyncSession) -> EventLookup:
    """Eventos de `commercial`, consultados por su `public_api` (AGENTS.md, regla 3)."""
    return commercial_event_lookup(session)
