"""Casos de uso: dar de baja y reactivar un trabajador (HU15, CA-15.9/CA-15.10).

La baja es lógica: se cambia el estado y nunca se borra la ficha (R-STF-2). El
cambio se audita con actor y fecha-hora solo cuando hubo un cambio real; repetir
la operación devuelve la ficha sin escribir otra fila de auditoría (plan §3).
Python puro: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from local_eventos.modules.staff.application.assignment_occupancy import (
    AssignmentOccupancy,
)
from local_eventos.modules.staff.application.errors import (
    WorkerHasFutureAssignmentsError,
    WorkerNotFoundError,
)
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerRepository,
)
from local_eventos.modules.staff.domain.audit import AuditAction, WorkerAudit
from local_eventos.modules.staff.domain.worker import Worker


class _ChangeWorkerStatus:
    """Base común: bloquea la ficha, aplica el cambio y audita si fue real."""

    _action: AuditAction

    def __init__(self, workers: WorkerRepository, clock: Clock) -> None:
        self._workers = workers
        self._clock = clock

    def _apply(self, worker: Worker) -> bool:
        raise NotImplementedError

    async def _before_apply(self, worker_id: UUID) -> datetime | None:
        """Gancho previo al cambio de estado; por defecto no hace nada.

        Se invoca después de bloquear la ficha y antes de `_apply`, de modo que
        un bloqueo (por ejemplo, asignaciones futuras vigentes) no escriba
        auditoría ni cambie el estado (CA-17.25). Puede devolver el instante que
        ya tomó del reloj para que la auditoría use exactamente el mismo.
        """
        return None

    async def execute(self, worker_id: UUID, reason: str | None, actor_id: UUID) -> Worker:
        """Cambia el estado y devuelve la ficha.

        Lanza `WorkerNotFoundError` si el id no existe. Si el trabajador ya está
        en el estado pedido, devuelve la ficha sin escribir auditoría (idempotente).
        """
        worker = await self._workers.get_for_update(worker_id)
        if worker is None:
            raise WorkerNotFoundError()

        now = await self._before_apply(worker_id)

        if not self._apply(worker):
            return worker

        audit = WorkerAudit(
            worker_id=worker.id,
            action=self._action,
            changed_by=actor_id,
            changed_at=now if now is not None else self._clock.now(),
            reason=reason,
        )
        await self._workers.save(worker, audit)
        return worker


class DeactivateWorker(_ChangeWorkerStatus):
    """Da de baja lógica al trabajador, con motivo opcional.

    Antes de cambiar el estado libera las asignaciones de eventos cancelados y
    rechaza la baja si quedan asignaciones futuras vigentes (CA-17.25, plan §3.5).
    """

    _action = AuditAction.DEACTIVATED

    def __init__(
        self,
        workers: WorkerRepository,
        clock: Clock,
        occupancy: AssignmentOccupancy,
    ) -> None:
        super().__init__(workers, clock)
        self._occupancy = occupancy

    async def _before_apply(self, worker_id: UUID) -> datetime:
        now = self._clock.now()
        await self._occupancy.release_cancelled(worker_id)
        if await self._occupancy.has_future(worker_id, now):
            raise WorkerHasFutureAssignmentsError()
        return now

    def _apply(self, worker: Worker) -> bool:
        return worker.deactivate()


class ActivateWorker(_ChangeWorkerStatus):
    """Reactiva al trabajador, con motivo opcional."""

    _action = AuditAction.ACTIVATED

    def _apply(self, worker: Worker) -> bool:
        return worker.activate()
