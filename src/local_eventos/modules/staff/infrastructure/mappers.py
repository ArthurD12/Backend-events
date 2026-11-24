"""Mapeo explícito entre el dominio de `staff` y sus filas ORM (HU15).

El dominio no conoce SQLAlchemy (AGENTS.md, regla 2): estas funciones son el único
punto que traduce `Worker`/`WorkerAudit` a filas y viceversa. Los nulos y los enums
se convierten de forma explícita para que el roundtrip sea exacto.
"""

from __future__ import annotations

from local_eventos.modules.staff.domain.audit import AuditAction, WorkerAudit
from local_eventos.modules.staff.domain.document import Document, DocumentType
from local_eventos.modules.staff.domain.enums import (
    WorkerFunction,
    WorkerStatus,
    WorkerType,
)
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.orm_models import (
    StaffWorkerAuditRow,
    StaffWorkerRow,
)


def worker_to_row(worker: Worker) -> StaffWorkerRow:
    """Crea una fila nueva a partir de la ficha de dominio."""
    row = StaffWorkerRow(id=worker.id)
    apply_worker_to_row(worker, row)
    return row


def apply_worker_to_row(worker: Worker, row: StaffWorkerRow) -> None:
    """Copia los campos editables de la ficha a una fila existente."""
    row.name = worker.name
    row.document_type = worker.document.type.value
    row.document_number = worker.document.number
    row.phone = worker.phone
    row.worker_function = None if worker.function is None else worker.function.value
    row.function_description = worker.function_description
    row.worker_type = None if worker.worker_type is None else worker.worker_type.value
    row.rate_cents = None if worker.rate is None else worker.rate.cents
    row.overtime_applies = worker.overtime_applies
    row.overtime_rate_cents = (
        None if worker.overtime_rate is None else worker.overtime_rate.cents
    )
    row.status = worker.status.value


def worker_from_row(row: StaffWorkerRow) -> Worker:
    """Reconstruye la ficha de dominio desde la fila, incluidos los opcionales nulos."""
    return Worker(
        id=row.id,
        name=row.name,
        document=Document(DocumentType(row.document_type), row.document_number),
        phone=row.phone,
        function=None if row.worker_function is None else WorkerFunction(row.worker_function),
        function_description=row.function_description,
        worker_type=None if row.worker_type is None else WorkerType(row.worker_type),
        rate=None if row.rate_cents is None else Money(row.rate_cents),
        overtime_applies=row.overtime_applies,
        overtime_rate=None
        if row.overtime_rate_cents is None
        else Money(row.overtime_rate_cents),
        status=WorkerStatus(row.status),
    )


def audit_to_row(audit: WorkerAudit) -> StaffWorkerAuditRow:
    """Crea la fila de auditoría; nunca se actualiza, solo se inserta."""
    return StaffWorkerAuditRow(
        worker_id=audit.worker_id,
        action=audit.action.value,
        reason=audit.reason,
        changed_by=audit.changed_by,
        changed_at=audit.changed_at,
    )


def audit_from_row(row: StaffWorkerAuditRow) -> WorkerAudit:
    """Reconstruye la operación auditada desde la fila."""
    return WorkerAudit(
        worker_id=row.worker_id,
        action=AuditAction(row.action),
        reason=row.reason,
        changed_by=row.changed_by,
        changed_at=row.changed_at,
    )
