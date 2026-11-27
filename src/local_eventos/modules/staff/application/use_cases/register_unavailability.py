"""Caso de uso: registrar una indisponibilidad de un trabajador (HU16, T-05).

Flujo (plan §3.2): el trabajador debe existir (`staff.not_found`, 404) y estar
`ACTIVE` (`staff.worker_inactive`, 409, CA-16.2); la fecha y las horas locales de
Lima se convierten a una ventana UTC semiabierta con `UnavailabilitySchedule`
(R-ASG-4, cruce de medianoche); el agregado valida tipo y descripción (CA-16.1) y
nace `ACTIVE`. Se crea la auditoría `CREATED` con el actor y el instante del reloj
inyectado y se guardan **ambos en una sola llamada** al repositorio (plan §5.5).

Python puro: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import time
from uuid import UUID

from local_eventos.modules.staff.application.errors import (
    WorkerInactiveError,
    WorkerNotFoundError,
)
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.unavailability_repository import (
    UnavailabilityRepository,
)
from local_eventos.modules.staff.application.ports.worker_repository import WorkerLookup
from local_eventos.modules.staff.domain.enums import UnavailabilityKind, WorkerStatus
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.unavailability_audit import UnavailabilityAudit
from local_eventos.modules.staff.domain.unavailability_schedule import (
    UnavailabilitySchedule,
)

__all__ = ["RegisterUnavailability"]


class RegisterUnavailability:
    """Registra una indisponibilidad activa y audita el alta."""

    def __init__(
        self,
        workers: WorkerLookup,
        unavailabilities: UnavailabilityRepository,
        clock: Clock,
    ) -> None:
        self._workers = workers
        self._unavailabilities = unavailabilities
        self._clock = clock

    async def execute(
        self,
        *,
        worker_id: UUID,
        date: date_type,
        start_time: time,
        end_time: time,
        kind: UnavailabilityKind | None,
        description: str | None,
        actor_id: UUID,
    ) -> Unavailability:
        """Crea la indisponibilidad y devuelve el agregado persistido.

        Lanza `WorkerNotFoundError` (404, `staff.not_found`), `WorkerInactiveError`
        (409, `staff.worker_inactive`) y los errores de validación del dominio
        (`staff.unavailability_schedule_invalid`, `staff.unavailability_kind_required`,
        `staff.unavailability_description_*`, 422).
        """
        worker = await self._workers.get(worker_id)
        if worker is None:
            raise WorkerNotFoundError()
        if worker.status is not WorkerStatus.ACTIVE:
            raise WorkerInactiveError()

        schedule = UnavailabilitySchedule(
            date=date,
            start_time=start_time,
            end_time=end_time,
        )
        unavailability = Unavailability.register(
            worker_id=worker_id,
            kind=kind,
            start_at=schedule.start_at,
            end_at=schedule.end_at,
            description=description,
        )
        audit = UnavailabilityAudit.created(
            unavailability_id=unavailability.id,
            actor_id=actor_id,
            occurred_at=self._clock.now(),
        )
        await self._unavailabilities.save(unavailability, audit)
        return unavailability
