"""Pruebas de `AssignmentAudit` y `AssignmentSnapshot` (HU17, R-ASG-8/R-ASG-9).

Sin base de datos: dominio puro.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import (
    AssignmentAction,
    AssignmentAudit,
    AssignmentSnapshot,
)
from local_eventos.modules.staff.domain.enums import WorkerFunction
from local_eventos.modules.staff.domain.errors import (
    AssignmentReasonRequiredError,
    StaffValidationError,
)
from local_eventos.modules.staff.domain.money import Money

ASSIGNMENT_ID = UUID("22222222-2222-2222-2222-222222222222")
ACTOR_ID = UUID("99999999-9999-9999-9999-999999999999")
EVENT_ID = UUID("33333333-3333-3333-3333-333333333333")
WORKER_ID = UUID("44444444-4444-4444-4444-444444444444")
START_AT = datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
END_AT = datetime(2026, 11, 25, 22, 0, tzinfo=UTC)
OCCURRED_AT = datetime(2026, 11, 20, 10, 30, tzinfo=UTC)


def _snapshot(**overrides: object) -> AssignmentSnapshot:
    data: dict[str, object] = {
        "function": WorkerFunction.WAITER,
        "function_description": None,
        "start_at": START_AT,
        "end_at": END_AT,
        "pay_cents": 4500,
        "currency": "PEN",
    }
    data.update(overrides)
    return AssignmentSnapshot(**data)  # type: ignore[arg-type]


def _assignment() -> Assignment:
    return Assignment.register(
        event_id=EVENT_ID,
        worker_id=WORKER_ID,
        function=WorkerFunction.OTHER,
        function_description="Bartender de autor",
        start_at=START_AT,
        end_at=END_AT,
        pay=Money(7250),
        assignment_id=ASSIGNMENT_ID,
    )


# --- AssignmentSnapshot ---------------------------------------------------


def test_snapshot_valido_normaliza_instantes_a_utc() -> None:
    lima = timezone(timedelta(hours=-5))
    snapshot = _snapshot(
        start_at=datetime(2026, 11, 25, 9, 0, tzinfo=lima),
        end_at=datetime(2026, 11, 25, 17, 0, tzinfo=lima),
    )

    assert snapshot.start_at == START_AT
    assert snapshot.end_at == END_AT
    assert snapshot.start_at.tzinfo is UTC
    assert snapshot.pay_cents == 4500
    assert snapshot.currency == "PEN"


@pytest.mark.parametrize("pay_cents", [-1, 12.5, "4500", True])
def test_snapshot_pago_invalido(pay_cents: object) -> None:
    with pytest.raises(StaffValidationError) as error:
        _snapshot(pay_cents=pay_cents)

    assert error.value.code == "staff.audit_invalid"


@pytest.mark.parametrize("currency", ["USD", "EUR", ""])
def test_snapshot_moneda_invalida(currency: str) -> None:
    with pytest.raises(StaffValidationError) as error:
        _snapshot(currency=currency)

    assert error.value.code == "staff.audit_invalid"


@pytest.mark.parametrize("naive", [datetime(2026, 11, 25, 14, 0)])
def test_snapshot_fechas_deben_incluir_zona(naive: datetime) -> None:
    with pytest.raises(StaffValidationError) as error:
        _snapshot(start_at=naive)

    assert error.value.code == "staff.audit_invalid"


def test_snapshot_round_trip_desde_assignment_snapshot() -> None:
    assignment = _assignment()

    snapshot = AssignmentSnapshot.from_mapping(assignment.snapshot())

    assert snapshot.to_dict() == assignment.snapshot()
    assert snapshot.function is WorkerFunction.OTHER
    assert snapshot.function_description == "Bartender de autor"
    assert snapshot.pay_cents == 7250


def test_snapshot_from_mapping_exige_todas_las_claves() -> None:
    with pytest.raises(StaffValidationError) as error:
        AssignmentSnapshot.from_mapping({"function": "WAITER"})

    assert error.value.code == "staff.audit_invalid"


def test_snapshot_es_inmutable() -> None:
    snapshot = _snapshot()

    with pytest.raises(FrozenInstanceError):
        snapshot.pay_cents = 1  # type: ignore[misc]


# --- AssignmentAudit: CREATED --------------------------------------------


def test_created_sin_motivo_ni_snapshots() -> None:
    audit = AssignmentAudit.created(
        assignment_id=ASSIGNMENT_ID, actor_id=ACTOR_ID, occurred_at=OCCURRED_AT
    )

    assert audit.action is AssignmentAction.CREATED
    assert audit.reason is None
    assert audit.previous_values is None
    assert audit.new_values is None


def test_created_rechaza_motivo() -> None:
    with pytest.raises(StaffValidationError) as error:
        AssignmentAudit(
            assignment_id=ASSIGNMENT_ID,
            action=AssignmentAction.CREATED,
            actor_id=ACTOR_ID,
            occurred_at=OCCURRED_AT,
            reason="no aplica",
        )

    assert error.value.code == "staff.audit_reason_not_allowed"


def test_created_rechaza_snapshots() -> None:
    with pytest.raises(StaffValidationError) as error:
        AssignmentAudit(
            assignment_id=ASSIGNMENT_ID,
            action=AssignmentAction.CREATED,
            actor_id=ACTOR_ID,
            occurred_at=OCCURRED_AT,
            new_values=_snapshot(),
        )

    assert error.value.code == "staff.audit_invalid"


# --- AssignmentAudit: UPDATED --------------------------------------------


def test_updated_con_motivo_y_snapshots() -> None:
    audit = AssignmentAudit.updated(
        assignment_id=ASSIGNMENT_ID,
        actor_id=ACTOR_ID,
        occurred_at=OCCURRED_AT,
        reason="  Ajuste de horario  ",
        previous_values=_snapshot(),
        new_values=_snapshot(pay_cents=6000),
    )

    assert audit.action is AssignmentAction.UPDATED
    assert audit.reason == "Ajuste de horario"
    assert audit.previous_values == _snapshot()
    assert audit.new_values == _snapshot(pay_cents=6000)


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_updated_sin_motivo_es_invalido(reason: str | None) -> None:
    with pytest.raises(AssignmentReasonRequiredError) as error:
        AssignmentAudit(
            assignment_id=ASSIGNMENT_ID,
            action=AssignmentAction.UPDATED,
            actor_id=ACTOR_ID,
            occurred_at=OCCURRED_AT,
            reason=reason,
            previous_values=_snapshot(),
            new_values=_snapshot(),
        )

    assert error.value.code == "staff.assignment_reason_required"


def test_updated_exige_snapshots() -> None:
    with pytest.raises(StaffValidationError) as error:
        AssignmentAudit.updated(
            assignment_id=ASSIGNMENT_ID,
            actor_id=ACTOR_ID,
            occurred_at=OCCURRED_AT,
            reason="Cambio",
            previous_values=None,  # type: ignore[arg-type]
            new_values=_snapshot(),
        )

    assert error.value.code == "staff.audit_invalid"


# --- AssignmentAudit: CANCELLED ------------------------------------------


def test_cancelled_con_motivo_y_sin_snapshots() -> None:
    audit = AssignmentAudit.cancelled(
        assignment_id=ASSIGNMENT_ID,
        actor_id=ACTOR_ID,
        occurred_at=OCCURRED_AT,
        reason="Evento cancelado",
    )

    assert audit.action is AssignmentAction.CANCELLED
    assert audit.reason == "Evento cancelado"
    assert audit.previous_values is None
    assert audit.new_values is None


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_cancelled_sin_motivo_es_invalido(reason: str | None) -> None:
    with pytest.raises(AssignmentReasonRequiredError) as error:
        AssignmentAudit.cancelled(
            assignment_id=ASSIGNMENT_ID,
            actor_id=ACTOR_ID,
            occurred_at=OCCURRED_AT,
            reason=reason,  # type: ignore[arg-type]
        )

    assert error.value.code == "staff.assignment_reason_required"


def test_cancelled_rechaza_snapshots() -> None:
    with pytest.raises(StaffValidationError) as error:
        AssignmentAudit(
            assignment_id=ASSIGNMENT_ID,
            action=AssignmentAction.CANCELLED,
            actor_id=ACTOR_ID,
            occurred_at=OCCURRED_AT,
            reason="Anulada",
            previous_values=_snapshot(),
        )

    assert error.value.code == "staff.audit_invalid"


# --- AssignmentAudit: validaciones generales -----------------------------


def test_occurred_at_normaliza_a_utc() -> None:
    lima = timezone(timedelta(hours=-5))
    audit = AssignmentAudit.created(
        assignment_id=ASSIGNMENT_ID,
        actor_id=ACTOR_ID,
        occurred_at=datetime(2026, 11, 20, 5, 30, tzinfo=lima),
    )

    assert audit.occurred_at == OCCURRED_AT
    assert audit.occurred_at.tzinfo is UTC


def test_occurred_at_debe_incluir_zona() -> None:
    with pytest.raises(StaffValidationError) as error:
        AssignmentAudit.created(
            assignment_id=ASSIGNMENT_ID,
            actor_id=ACTOR_ID,
            occurred_at=datetime(2026, 11, 20, 10, 30),
        )

    assert error.value.code == "staff.audit_invalid"


def test_actor_y_asignacion_deben_ser_uuid() -> None:
    with pytest.raises(StaffValidationError):
        AssignmentAudit.created(
            assignment_id="no-uuid",  # type: ignore[arg-type]
            actor_id=ACTOR_ID,
            occurred_at=OCCURRED_AT,
        )
    with pytest.raises(StaffValidationError):
        AssignmentAudit.created(
            assignment_id=ASSIGNMENT_ID,
            actor_id="no-uuid",  # type: ignore[arg-type]
            occurred_at=OCCURRED_AT,
        )


def test_audit_es_inmutable() -> None:
    audit = AssignmentAudit.created(
        assignment_id=ASSIGNMENT_ID, actor_id=ACTOR_ID, occurred_at=OCCURRED_AT
    )

    with pytest.raises(FrozenInstanceError):
        audit.reason = "cambio"  # type: ignore[misc]


def test_no_depende_de_identity_ni_commercial() -> None:
    # El actor es un UUID plano; no se importan módulos de identity/commercial.
    audit = AssignmentAudit.cancelled(
        assignment_id=ASSIGNMENT_ID,
        actor_id=uuid4(),
        occurred_at=OCCURRED_AT,
        reason="Anulada",
    )

    assert isinstance(audit.actor_id, UUID)
