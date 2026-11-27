"""Pruebas del mapeo ORM ⇄ dominio de personal (HU15, T-09). Sin base de datos."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import (
    AssignmentAudit,
    AssignmentSnapshot,
)
from local_eventos.modules.staff.domain.audit import AuditAction, WorkerAudit
from local_eventos.modules.staff.domain.document import Document, WorkerDocumentType
from local_eventos.modules.staff.domain.enums import (
    AssignmentStatus,
    WorkerFunction,
    WorkerStatus,
    WorkerType,
)
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.mappers import (
    assignment_audit_to_row,
    assignment_to_row,
    audit_from_row,
    audit_to_row,
    row_to_assignment,
    row_to_assignment_audit,
    worker_from_row,
    worker_to_row,
)
from local_eventos.modules.staff.infrastructure.orm_models import (
    StaffAssignmentAuditRow,
    StaffAssignmentRow,
    StaffWorkerAuditRow,
    StaffWorkerRow,
)

WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")
ACTOR_ID = UUID("22222222-2222-2222-2222-222222222222")
CHANGED_AT = datetime(2026, 11, 24, 15, 30, tzinfo=UTC)
EVENT_ID = UUID("33333333-3333-3333-3333-333333333333")
ASSIGNMENT_ID = UUID("44444444-4444-4444-4444-444444444444")
START_AT = datetime(2026, 12, 5, 15, 0, tzinfo=UTC)
END_AT = datetime(2026, 12, 5, 23, 0, tzinfo=UTC)

_STAFF_WORKER_COLUMNS = {
    "id",
    "name",
    "document_type",
    "document_number",
    "phone",
    "worker_function",
    "function_description",
    "worker_type",
    "rate_cents",
    "overtime_applies",
    "overtime_rate_cents",
    "status",
    "created_at",
    "updated_at",
}
_STAFF_WORKER_AUDIT_COLUMNS = {
    "id",
    "worker_id",
    "action",
    "reason",
    "changed_by",
    "changed_at",
}
_STAFF_ASSIGNMENT_COLUMNS = {
    "id",
    "event_id",
    "worker_id",
    "worker_function",
    "function_description",
    "start_at",
    "end_at",
    "pay_cents",
    "currency",
    "status",
    "occupies",
    "created_at",
    "updated_at",
}
_STAFF_ASSIGNMENT_AUDIT_COLUMNS = {
    "id",
    "assignment_id",
    "action",
    "reason",
    "actor_id",
    "occurred_at",
    "previous_values",
    "new_values",
}


def test_roundtrip_ficha_completa() -> None:
    worker = Worker.register(
        worker_id=WORKER_ID,
        name="Ana Torres",
        document_type=WorkerDocumentType.CE,
        document_number="123456789",
        phone="987654321",
        function=WorkerFunction.OTHER,
        function_description="Sommelier",
        worker_type=WorkerType.FIXED,
        rate=Money(15000),
        overtime_applies=True,
        overtime_rate=Money(2500),
    )

    row = worker_to_row(worker)

    assert row.document_type == "CE"
    assert row.document_number == "123456789"
    assert row.worker_function == "OTHER"
    assert row.worker_type == "FIXED"
    assert row.rate_cents == 15000
    assert row.overtime_rate_cents == 2500
    assert row.status == "ACTIVE"
    assert worker_from_row(row) == worker


def test_roundtrip_ficha_minima_con_opcionales_nulos() -> None:
    worker = Worker.register(
        worker_id=WORKER_ID,
        name="Luis Ramos",
        document_type=WorkerDocumentType.DNI,
        document_number="44125896",
    )

    row = worker_to_row(worker)

    assert row.phone is None
    assert row.worker_function is None
    assert row.function_description is None
    assert row.worker_type is None
    assert row.rate_cents is None
    assert row.overtime_applies is False
    assert row.overtime_rate_cents is None
    assert worker_from_row(row) == worker


def test_roundtrip_auditoria_con_motivo() -> None:
    audit = WorkerAudit(
        worker_id=WORKER_ID,
        action=AuditAction.DEACTIVATED,
        reason="Renuncia",
        changed_by=ACTOR_ID,
        changed_at=CHANGED_AT,
    )

    row = audit_to_row(audit)

    assert row.action == "DEACTIVATED"
    assert row.reason == "Renuncia"
    assert audit_from_row(row) == audit


def test_roundtrip_auditoria_sin_motivo() -> None:
    audit = WorkerAudit(
        worker_id=WORKER_ID,
        action=AuditAction.CREATED,
        changed_by=ACTOR_ID,
        changed_at=CHANGED_AT,
    )

    row = audit_to_row(audit)

    assert row.reason is None
    assert audit_from_row(row) == audit


def test_las_tablas_no_exponen_campos_de_mas() -> None:
    assert set(StaffWorkerRow.__table__.columns.keys()) == _STAFF_WORKER_COLUMNS
    assert set(StaffWorkerAuditRow.__table__.columns.keys()) == _STAFF_WORKER_AUDIT_COLUMNS
    assert set(StaffAssignmentRow.__table__.columns.keys()) == _STAFF_ASSIGNMENT_COLUMNS
    assert set(StaffAssignmentAuditRow.__table__.columns.keys()) == _STAFF_ASSIGNMENT_AUDIT_COLUMNS


def test_documento_se_normaliza_al_reconstruir() -> None:
    worker = Worker.register(
        worker_id=WORKER_ID,
        name="Luis Ramos",
        document_type=WorkerDocumentType.DNI,
        document_number="44125896",
    )
    row = worker_to_row(worker)
    row.document_number = "44125896"

    rebuilt = worker_from_row(row)

    assert rebuilt.document == Document(WorkerDocumentType.DNI, "44125896")
    assert rebuilt.status is WorkerStatus.ACTIVE


def test_roundtrip_asignacion_completa_utc() -> None:
    assignment = Assignment.register(
        assignment_id=ASSIGNMENT_ID,
        event_id=EVENT_ID,
        worker_id=WORKER_ID,
        function=WorkerFunction.OTHER,
        function_description="Sommelier",
        start_at=START_AT,
        end_at=END_AT,
        pay=Money(12500),
    )

    row = assignment_to_row(assignment)

    assert row.id == ASSIGNMENT_ID
    assert row.event_id == EVENT_ID
    assert row.worker_id == WORKER_ID
    assert row.worker_function == "OTHER"
    assert row.function_description == "Sommelier"
    assert row.start_at == START_AT
    assert row.end_at == END_AT
    assert row.pay_cents == 12500
    assert row.currency == "PEN"
    assert row.status == "ACTIVE"
    assert row.occupies is True
    assert row_to_assignment(row) == assignment


def test_roundtrip_asignacion_sin_descripcion_y_pago_cero() -> None:
    assignment = Assignment.register(
        assignment_id=ASSIGNMENT_ID,
        event_id=EVENT_ID,
        worker_id=WORKER_ID,
        function=WorkerFunction.WAITER,
        start_at=START_AT,
        end_at=END_AT,
        pay=0,
    )

    row = assignment_to_row(assignment)

    assert row.function_description is None
    assert row.pay_cents == 0
    assert row_to_assignment(row) == assignment


def test_mapeo_asignacion_cancelada() -> None:
    assignment = Assignment.register(
        assignment_id=ASSIGNMENT_ID,
        event_id=EVENT_ID,
        worker_id=WORKER_ID,
        function=WorkerFunction.COOK,
        start_at=START_AT,
        end_at=END_AT,
        pay=8000,
    )
    assignment.cancel()

    row = assignment_to_row(assignment)

    assert row.status == "CANCELLED"
    assert row.occupies is False
    rebuilt = row_to_assignment(row)
    assert rebuilt.status is AssignmentStatus.CANCELLED
    assert rebuilt.occupies is False


def test_roundtrip_auditoria_actualizacion_con_snapshots() -> None:
    previous = AssignmentSnapshot(
        function=WorkerFunction.WAITER,
        function_description=None,
        start_at=START_AT,
        end_at=END_AT,
        pay_cents=8000,
    )
    new = AssignmentSnapshot(
        function=WorkerFunction.COOK,
        function_description=None,
        start_at=START_AT,
        end_at=END_AT,
        pay_cents=9000,
    )
    audit = AssignmentAudit.updated(
        assignment_id=ASSIGNMENT_ID,
        actor_id=ACTOR_ID,
        occurred_at=CHANGED_AT,
        reason="Cambio de función y pago",
        previous_values=previous,
        new_values=new,
    )

    row = assignment_audit_to_row(audit)

    assert row.action == "UPDATED"
    assert row.reason == "Cambio de función y pago"
    assert row.previous_values == previous.to_dict()
    assert row.new_values == new.to_dict()
    assert row_to_assignment_audit(row) == audit
