"""Caso de uso: dar de alta un trabajador (HU15, CA-15.1/CA-15.3/CA-15.16).

Valida los datos con el agregado, rechaza documentos ya usados —incluidos los de
trabajadores inactivos— y guarda la ficha junto con su auditoría en la misma
transacción (plan §4). Python puro: sin FastAPI, SQLAlchemy ni Pydantic.
"""

from __future__ import annotations

from uuid import UUID

from local_eventos.modules.staff.application.errors import DuplicateDocumentError
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerRepository,
)
from local_eventos.modules.staff.application.use_cases.worker_data import WorkerData
from local_eventos.modules.staff.domain.audit import AuditAction, WorkerAudit
from local_eventos.modules.staff.domain.worker import Worker


class RegisterWorker:
    """Registra un trabajador nuevo, siempre activo, y audita el alta."""

    def __init__(self, workers: WorkerRepository, clock: Clock) -> None:
        self._workers = workers
        self._clock = clock

    async def execute(self, data: WorkerData, actor_id: UUID) -> Worker:
        """Crea la ficha y devuelve el trabajador persistido.

        Lanza `StaffValidationError` si los datos no cumplen el dominio y
        `DuplicateDocumentError` si otro trabajador —activo o inactivo— ya usa
        la combinación tipo + número.
        """
        worker = Worker.register(
            name=data.name,
            document_type=data.document_type,
            document_number=data.document_number,
            phone=data.phone,
            function=data.function,
            function_description=data.function_description,
            worker_type=data.worker_type,
            rate=data.rate,
            overtime_applies=data.overtime_applies,
            overtime_rate=data.overtime_rate,
        )

        existing = await self._workers.get_by_document(worker.document)
        if existing is not None:
            raise DuplicateDocumentError(worker.document)

        audit = WorkerAudit(
            worker_id=worker.id,
            action=AuditAction.CREATED,
            changed_by=actor_id,
            changed_at=self._clock.now(),
        )
        await self._workers.save(worker, audit)
        return worker
