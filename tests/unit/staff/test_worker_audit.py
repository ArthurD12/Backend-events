"""Pruebas de la auditoría del trabajador (HU15, CA-15.16/CA-15.24). Sin base de datos."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from local_eventos.modules.staff.domain.audit import AuditAction, WorkerAudit
from local_eventos.modules.staff.domain.errors import StaffValidationError

WORKER_ID = uuid4()
ACTOR_ID = uuid4()
NOW = datetime(2026, 11, 24, 15, 30, tzinfo=UTC)


def make_audit(
    action: AuditAction,
    reason: str | None = None,
) -> WorkerAudit:
    return WorkerAudit(
        worker_id=WORKER_ID,
        action=action,
        changed_by=ACTOR_ID,
        changed_at=NOW,
        reason=reason,
    )


@pytest.mark.parametrize("action", list(AuditAction))
def test_acciones_validas(action: AuditAction) -> None:
    audit = make_audit(action)

    assert audit.action is action
    assert audit.worker_id == WORKER_ID
    assert audit.changed_by == ACTOR_ID
    assert audit.changed_at == NOW
    assert audit.reason is None


@pytest.mark.parametrize("action", [AuditAction.ACTIVATED, AuditAction.DEACTIVATED])
def test_razon_permitida_en_cambios_de_estado(action: AuditAction) -> None:
    assert make_audit(action, "  Autorizado por gerencia  ").reason == ("Autorizado por gerencia")


@pytest.mark.parametrize("action", [AuditAction.CREATED, AuditAction.UPDATED])
def test_razon_prohibida_en_alta_y_edicion(action: AuditAction) -> None:
    with pytest.raises(StaffValidationError) as error:
        make_audit(action, "no aplica")
    assert error.value.code == "staff.audit_reason_not_allowed"


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_razon_vacia_se_normaliza_a_none(reason: str | None) -> None:
    assert make_audit(AuditAction.DEACTIVATED, reason).reason is None


def test_changed_at_exige_zona_horaria() -> None:
    naive = datetime(2026, 11, 24, 15, 30)
    with pytest.raises(StaffValidationError) as error:
        WorkerAudit(
            worker_id=WORKER_ID,
            action=AuditAction.CREATED,
            changed_by=ACTOR_ID,
            changed_at=naive,
        )
    assert error.value.code == "staff.audit_invalid"


@pytest.mark.parametrize("field", ["worker_id", "changed_by"])
def test_actor_y_trabajador_deben_ser_uuid(field: str) -> None:
    values: dict[str, object] = {
        "worker_id": WORKER_ID,
        "action": AuditAction.CREATED,
        "changed_by": ACTOR_ID,
        "changed_at": NOW,
    }
    values[field] = "no-es-uuid"
    with pytest.raises(StaffValidationError) as error:
        WorkerAudit(**values)  # type: ignore[arg-type]
    assert error.value.code == "staff.audit_invalid"


def test_accion_invalida_se_rechaza() -> None:
    with pytest.raises(StaffValidationError) as error:
        WorkerAudit(
            worker_id=WORKER_ID,
            action="DELETED",  # type: ignore[arg-type]
            changed_by=ACTOR_ID,
            changed_at=NOW,
        )
    assert error.value.code == "staff.audit_invalid"


def test_auditoria_es_inmutable() -> None:
    audit = make_audit(AuditAction.UPDATED)

    with pytest.raises(FrozenInstanceError):
        audit.reason = "cambio"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        audit.action = AuditAction.CREATED  # type: ignore[misc]


def test_worker_audit_expone_los_campos_del_contrato() -> None:
    audit = make_audit(AuditAction.DEACTIVATED, "renuncia")

    assert set(audit.__dataclass_fields__) == {
        "worker_id",
        "action",
        "changed_by",
        "changed_at",
        "reason",
    }
    assert isinstance(audit.worker_id, UUID)
