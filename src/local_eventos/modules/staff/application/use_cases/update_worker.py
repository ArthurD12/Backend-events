"""Caso de uso: editar los datos de un trabajador (HU15, CA-15.4/CA-15.6/CA-15.16).

Bloquea la ficha, rechaza documentos usados por otro trabajador —incluidos los
inactivos— y guarda el cambio con su auditoría en la misma transacción. Python
puro: sin FastAPI, SQLAlchemy ni Pydantic.
"""

from __future__ import annotations

from uuid import UUID

from local_eventos.modules.staff.application.errors import (
    DuplicateDocumentError,
    WorkerNotFoundError,
)
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerRepository,
)
from local_eventos.modules.staff.application.use_cases.worker_data import WorkerData
from local_eventos.modules.staff.domain.audit import AuditAction, WorkerAudit
from local_eventos.modules.staff.domain.document import Document
from local_eventos.modules.staff.domain.worker import Worker


class UpdateWorker:
    """Reemplaza los datos editables y audita la edición."""

    def __init__(self, workers: WorkerRepository, clock: Clock) -> None:
        self._workers = workers
        self._clock = clock

    async def execute(self, worker_id: UUID, data: WorkerData, actor_id: UUID) -> Worker:
        """Actualiza la ficha y devuelve el trabajador persistido.

        Lanza `WorkerNotFoundError` si el id no existe, `StaffValidationError` si
        los datos no cumplen el dominio y `DuplicateDocumentError` si otro
        trabajador ya usa el documento; en ese caso la ficha no se modifica.
        """
        worker = await self._workers.get_for_update(worker_id)
        if worker is None:
            raise WorkerNotFoundError()

        document = Document(data.document_type, data.document_number)
        existing = await self._workers.get_by_document(document)
        if existing is not None and existing.id != worker_id:
            raise DuplicateDocumentError(document)

        worker.update(
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

        audit = WorkerAudit(
            worker_id=worker.id,
            action=AuditAction.UPDATED,
            changed_by=actor_id,
            changed_at=self._clock.now(),
        )
        await self._workers.save(worker, audit)
        return worker
