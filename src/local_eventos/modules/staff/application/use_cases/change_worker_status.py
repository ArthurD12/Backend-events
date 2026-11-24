"""Casos de uso: dar de baja y reactivar un trabajador (HU15, CA-15.9/CA-15.10).

La baja es lógica: se cambia el estado y nunca se borra la ficha (R-STF-2). El
cambio se audita con actor y fecha-hora solo cuando hubo un cambio real; repetir
la operación devuelve la ficha sin escribir otra fila de auditoría (plan §3).
Python puro: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from uuid import UUID

from local_eventos.modules.staff.application.errors import WorkerNotFoundError
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

    async def execute(
        self, worker_id: UUID, reason: str | None, actor_id: UUID
    ) -> Worker:
        """Cambia el estado y devuelve la ficha.

        Lanza `WorkerNotFoundError` si el id no existe. Si el trabajador ya está
        en el estado pedido, devuelve la ficha sin escribir auditoría (idempotente).
        """
        worker = await self._workers.get_for_update(worker_id)
        if worker is None:
            raise WorkerNotFoundError()

        if not self._apply(worker):
            return worker

        audit = WorkerAudit(
            worker_id=worker.id,
            action=self._action,
            changed_by=actor_id,
            changed_at=self._clock.now(),
            reason=reason,
        )
        await self._workers.save(worker, audit)
        return worker


class DeactivateWorker(_ChangeWorkerStatus):
    """Da de baja lógica al trabajador, con motivo opcional."""

    _action = AuditAction.DEACTIVATED

    def _apply(self, worker: Worker) -> bool:
        return worker.deactivate()


class ActivateWorker(_ChangeWorkerStatus):
    """Reactiva al trabajador, con motivo opcional."""

    _action = AuditAction.ACTIVATED

    def _apply(self, worker: Worker) -> bool:
        return worker.activate()
