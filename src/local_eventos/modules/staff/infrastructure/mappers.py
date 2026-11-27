"""Mapeo explícito entre el dominio de `staff` y sus filas ORM (HU15, HU16, HU17).

El dominio no conoce SQLAlchemy (AGENTS.md, regla 2): estas funciones son el único
punto que traduce `Worker`/`WorkerAudit` a filas y viceversa. Los nulos y los enums
se convierten de forma explícita para que el roundtrip sea exacto.
"""

from __future__ import annotations

from datetime import UTC, datetime

from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import (
    AssignmentAction,
    AssignmentAudit,
    AssignmentSnapshot,
)
from local_eventos.modules.staff.domain.audit import AuditAction, WorkerAudit
from local_eventos.modules.staff.domain.document import Document, WorkerDocumentType
from local_eventos.modules.staff.domain.enums import (
    AssignmentStatus,
    UnavailabilityKind,
    UnavailabilityStatus,
    WorkerFunction,
    WorkerStatus,
    WorkerType,
)
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.unavailability_audit import (
    UnavailabilityAction,
    UnavailabilityAudit,
    UnavailabilitySnapshot,
)
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.orm_models import (
    StaffAssignmentAuditRow,
    StaffAssignmentRow,
    StaffUnavailabilityAuditRow,
    StaffUnavailabilityRow,
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
    row.overtime_rate_cents = None if worker.overtime_rate is None else worker.overtime_rate.cents
    row.status = worker.status.value


def worker_from_row(row: StaffWorkerRow) -> Worker:
    """Reconstruye la ficha de dominio desde la fila, incluidos los opcionales nulos."""
    return Worker(
        id=row.id,
        name=row.name,
        document=Document(WorkerDocumentType(row.document_type), row.document_number),
        phone=row.phone,
        function=None if row.worker_function is None else WorkerFunction(row.worker_function),
        function_description=row.function_description,
        worker_type=None if row.worker_type is None else WorkerType(row.worker_type),
        rate=None if row.rate_cents is None else Money(row.rate_cents),
        overtime_applies=row.overtime_applies,
        overtime_rate=None if row.overtime_rate_cents is None else Money(row.overtime_rate_cents),
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


def assignment_to_row(assignment: Assignment) -> StaffAssignmentRow:
    """Crea la fila de una asignación nueva; el pago se guarda en céntimos y la moneda."""
    return StaffAssignmentRow(
        id=assignment.id,
        event_id=assignment.event_id,
        worker_id=assignment.worker_id,
        worker_function=assignment.function.value,
        function_description=assignment.function_description,
        start_at=assignment.start_at,
        end_at=assignment.end_at,
        pay_cents=assignment.pay.cents,
        currency=assignment.pay.currency,
        status=assignment.status.value,
        occupies=assignment.occupies,
    )


def row_to_assignment(row: StaffAssignmentRow) -> Assignment:
    """Reconstruye la asignación desde la fila, con instantes normalizados a UTC."""
    return Assignment(
        id=row.id,
        event_id=row.event_id,
        worker_id=row.worker_id,
        function=WorkerFunction(row.worker_function),
        function_description=row.function_description,
        start_at=_as_utc(row.start_at),
        end_at=_as_utc(row.end_at),
        pay=Money(row.pay_cents, row.currency),
        status=AssignmentStatus(row.status),
        occupies=row.occupies,
    )


def assignment_audit_to_row(audit: AssignmentAudit) -> StaffAssignmentAuditRow:
    """Crea la fila de auditoría; los snapshots se serializan a JSON-compatible."""
    return StaffAssignmentAuditRow(
        assignment_id=audit.assignment_id,
        action=audit.action.value,
        reason=audit.reason,
        actor_id=audit.actor_id,
        occurred_at=audit.occurred_at,
        previous_values=(
            None if audit.previous_values is None else audit.previous_values.to_dict()
        ),
        new_values=None if audit.new_values is None else audit.new_values.to_dict(),
    )


def row_to_assignment_audit(row: StaffAssignmentAuditRow) -> AssignmentAudit:
    """Reconstruye la auditoría desde la fila, incluidos los snapshots JSONB."""
    return AssignmentAudit(
        assignment_id=row.assignment_id,
        action=AssignmentAction(row.action),
        reason=row.reason,
        actor_id=row.actor_id,
        occurred_at=_as_utc(row.occurred_at),
        previous_values=(
            None
            if row.previous_values is None
            else AssignmentSnapshot.from_mapping(row.previous_values)
        ),
        new_values=(
            None if row.new_values is None else AssignmentSnapshot.from_mapping(row.new_values)
        ),
    )


def unavailability_to_row(unavailability: Unavailability) -> StaffUnavailabilityRow:
    """Crea la fila de una indisponibilidad nueva; `created_at`/`updated_at` son técnicos."""
    return StaffUnavailabilityRow(
        id=unavailability.id,
        worker_id=unavailability.worker_id,
        kind=unavailability.kind.value,
        description=unavailability.description,
        start_at=unavailability.start_at,
        end_at=unavailability.end_at,
        status=unavailability.status.value,
    )


def row_to_unavailability(row: StaffUnavailabilityRow) -> Unavailability:
    """Reconstruye la indisponibilidad desde la fila, con instantes normalizados a UTC."""
    return Unavailability(
        id=row.id,
        worker_id=row.worker_id,
        kind=UnavailabilityKind(row.kind),
        description=row.description,
        start_at=_as_utc(row.start_at),
        end_at=_as_utc(row.end_at),
        status=UnavailabilityStatus(row.status),
    )


def unavailability_audit_to_row(audit: UnavailabilityAudit) -> StaffUnavailabilityAuditRow:
    """Crea la fila de auditoría; los snapshots se serializan a JSON-compatible."""
    return StaffUnavailabilityAuditRow(
        unavailability_id=audit.unavailability_id,
        action=audit.action.value,
        reason=audit.reason,
        actor_id=audit.actor_id,
        occurred_at=audit.occurred_at,
        previous_values=(
            None if audit.previous_values is None else audit.previous_values.to_dict()
        ),
        new_values=None if audit.new_values is None else audit.new_values.to_dict(),
    )


def row_to_unavailability_audit(row: StaffUnavailabilityAuditRow) -> UnavailabilityAudit:
    """Reconstruye la auditoría desde la fila, incluidos los snapshots JSONB."""
    return UnavailabilityAudit(
        unavailability_id=row.unavailability_id,
        action=UnavailabilityAction(row.action),
        reason=row.reason,
        actor_id=row.actor_id,
        occurred_at=_as_utc(row.occurred_at),
        previous_values=(
            None
            if row.previous_values is None
            else UnavailabilitySnapshot.from_mapping(row.previous_values)
        ),
        new_values=(
            None if row.new_values is None else UnavailabilitySnapshot.from_mapping(row.new_values)
        ),
    )


def _as_utc(value: datetime) -> datetime:
    """Normaliza un instante de la fila a UTC; asume UTC si llegara sin zona."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
