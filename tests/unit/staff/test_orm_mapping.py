"""Pruebas del mapeo ORM ⇄ dominio de personal (HU15, T-09). Sin base de datos."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from local_eventos.modules.staff.domain.audit import AuditAction, WorkerAudit
from local_eventos.modules.staff.domain.document import Document, DocumentType
from local_eventos.modules.staff.domain.enums import (
    WorkerFunction,
    WorkerStatus,
    WorkerType,
)
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.domain.worker import Worker
from local_eventos.modules.staff.infrastructure.mappers import (
    audit_from_row,
    audit_to_row,
    worker_from_row,
    worker_to_row,
)
from local_eventos.modules.staff.infrastructure.orm_models import (
    StaffWorkerAuditRow,
    StaffWorkerRow,
)

WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")
ACTOR_ID = UUID("22222222-2222-2222-2222-222222222222")
CHANGED_AT = datetime(2026, 11, 24, 15, 30, tzinfo=UTC)

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


def test_roundtrip_ficha_completa() -> None:
    worker = Worker.register(
        worker_id=WORKER_ID,
        name="Ana Torres",
        document_type=DocumentType.CE,
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
        document_type=DocumentType.DNI,
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


def test_documento_se_normaliza_al_reconstruir() -> None:
    worker = Worker.register(
        worker_id=WORKER_ID,
        name="Luis Ramos",
        document_type=DocumentType.DNI,
        document_number="44125896",
    )
    row = worker_to_row(worker)
    row.document_number = "44125896"

    rebuilt = worker_from_row(row)

    assert rebuilt.document == Document(DocumentType.DNI, "44125896")
    assert rebuilt.status is WorkerStatus.ACTIVE
