"""Pruebas del dominio de asistencia de personal (HU18, R-ATT-1/2/3/6/7/17/22).

Sin base de datos: dominio puro. Cubre CA-18.1, 18.2, 18.11, 18.12 y 18.16.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from local_eventos.modules.staff.domain.attendance import Attendance, AttendanceStatus
from local_eventos.modules.staff.domain.attendance_audit import (
    AttendanceAction,
    AttendanceAudit,
)
from local_eventos.modules.staff.domain.attendance_errors import (
    ATTENDANCE_REASON_REQUIRED,
    ATTENDANCE_STATUS_INVALID,
    AttendanceReasonRequiredError,
    AttendanceStatusInvalidError,
)
from local_eventos.modules.staff.domain.errors import StaffValidationError

ASSIGNMENT_ID = UUID("22222222-2222-2222-2222-222222222222")
ACTOR_ID = UUID("99999999-9999-9999-9999-999999999999")
OTHER_ACTOR_ID = UUID("88888888-8888-8888-8888-888888888888")
RECORDED_AT = datetime(2026, 11, 20, 10, 30, tzinfo=UTC)
CORRECTED_AT = datetime(2026, 11, 21, 8, 0, tzinfo=UTC)


def _record(status: AttendanceStatus = AttendanceStatus.ATTENDED) -> Attendance:
    attendance, _ = Attendance.record(
        assignment_id=ASSIGNMENT_ID,
        status=status,
        actor_id=ACTOR_ID,
        recorded_at=RECORDED_AT,
    )
    return attendance


# --- AttendanceStatus ------------------------------------------------------


def test_solo_existen_dos_estados() -> None:
    assert {status.value for status in AttendanceStatus} == {"ATTENDED", "NOT_ATTENDED"}


# --- Attendance.record -----------------------------------------------------


def test_record_crea_estado_y_auditoria_recorded() -> None:
    attendance, audit = Attendance.record(
        assignment_id=ASSIGNMENT_ID,
        status=AttendanceStatus.NOT_ATTENDED,
        actor_id=ACTOR_ID,
        recorded_at=RECORDED_AT,
    )

    assert attendance.assignment_id == ASSIGNMENT_ID
    assert attendance.status is AttendanceStatus.NOT_ATTENDED
    assert attendance.recorded_by == ACTOR_ID
    assert attendance.recorded_at == RECORDED_AT
    assert audit.action is AttendanceAction.RECORDED
    assert audit.new_status is AttendanceStatus.NOT_ATTENDED
    assert audit.previous_status is None
    assert audit.reason is None
    assert audit.actor_id == ACTOR_ID
    assert audit.occurred_at == RECORDED_AT


def test_record_normaliza_recorded_at_a_utc() -> None:
    lima = timezone(timedelta(hours=-5))
    attendance, audit = Attendance.record(
        assignment_id=ASSIGNMENT_ID,
        status=AttendanceStatus.ATTENDED,
        actor_id=ACTOR_ID,
        recorded_at=datetime(2026, 11, 20, 5, 30, tzinfo=lima),
    )

    assert attendance.recorded_at == RECORDED_AT
    assert attendance.recorded_at.tzinfo is UTC
    assert audit.occurred_at.tzinfo is UTC


@pytest.mark.parametrize("status", ["ATTENDED", "NOT_ATTENDED", None, "LATE", 1])
def test_record_rechaza_estado_invalido(status: object) -> None:
    with pytest.raises(AttendanceStatusInvalidError) as error:
        Attendance.record(
            assignment_id=ASSIGNMENT_ID,
            status=status,  # type: ignore[arg-type]
            actor_id=ACTOR_ID,
            recorded_at=RECORDED_AT,
        )

    assert error.value.code == ATTENDANCE_STATUS_INVALID


def test_record_exige_fecha_con_zona() -> None:
    with pytest.raises(StaffValidationError) as error:
        Attendance.record(
            assignment_id=ASSIGNMENT_ID,
            status=AttendanceStatus.ATTENDED,
            actor_id=ACTOR_ID,
            recorded_at=datetime(2026, 11, 20, 10, 30),
        )

    assert error.value.code == "staff.audit_invalid"


def test_record_exige_uuids() -> None:
    with pytest.raises(StaffValidationError):
        Attendance.record(
            assignment_id="no-uuid",  # type: ignore[arg-type]
            status=AttendanceStatus.ATTENDED,
            actor_id=ACTOR_ID,
            recorded_at=RECORDED_AT,
        )
    with pytest.raises(StaffValidationError):
        Attendance.record(
            assignment_id=ASSIGNMENT_ID,
            status=AttendanceStatus.ATTENDED,
            actor_id="no-uuid",  # type: ignore[arg-type]
            recorded_at=RECORDED_AT,
        )


# --- has_status ------------------------------------------------------------


def test_has_status_compara_el_estado_vigente() -> None:
    attendance = _record(AttendanceStatus.ATTENDED)

    assert attendance.has_status(AttendanceStatus.ATTENDED) is True
    assert attendance.has_status(AttendanceStatus.NOT_ATTENDED) is False


def test_has_status_rechaza_valor_invalido() -> None:
    attendance = _record()

    with pytest.raises(AttendanceStatusInvalidError):
        attendance.has_status("ATTENDED")  # type: ignore[arg-type]


# --- Attendance.correct ----------------------------------------------------


def test_correct_cambia_estado_y_devuelve_auditoria() -> None:
    attendance = _record(AttendanceStatus.ATTENDED)

    audit = attendance.correct(
        new_status=AttendanceStatus.NOT_ATTENDED,
        reason="  No se presentó  ",
        actor_id=OTHER_ACTOR_ID,
        occurred_at=CORRECTED_AT,
    )

    assert audit is not None
    assert audit.action is AttendanceAction.CORRECTED
    assert audit.previous_status is AttendanceStatus.ATTENDED
    assert audit.new_status is AttendanceStatus.NOT_ATTENDED
    assert audit.reason == "No se presentó"
    assert audit.actor_id == OTHER_ACTOR_ID
    assert audit.occurred_at == CORRECTED_AT
    assert attendance.status is AttendanceStatus.NOT_ATTENDED
    assert attendance.recorded_by == OTHER_ACTOR_ID
    assert attendance.recorded_at == CORRECTED_AT


def test_correct_al_mismo_estado_es_noop_sin_auditoria() -> None:
    attendance = _record(AttendanceStatus.ATTENDED)

    audit = attendance.correct(
        new_status=AttendanceStatus.ATTENDED,
        reason=None,
        actor_id=OTHER_ACTOR_ID,
        occurred_at=CORRECTED_AT,
    )

    assert audit is None
    assert attendance.status is AttendanceStatus.ATTENDED
    assert attendance.recorded_by == ACTOR_ID
    assert attendance.recorded_at == RECORDED_AT


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_correct_sin_motivo_no_muta(reason: str | None) -> None:
    attendance = _record(AttendanceStatus.ATTENDED)

    with pytest.raises(AttendanceReasonRequiredError) as error:
        attendance.correct(
            new_status=AttendanceStatus.NOT_ATTENDED,
            reason=reason,
            actor_id=OTHER_ACTOR_ID,
            occurred_at=CORRECTED_AT,
        )

    assert error.value.code == ATTENDANCE_REASON_REQUIRED
    assert attendance.status is AttendanceStatus.ATTENDED
    assert attendance.recorded_by == ACTOR_ID
    assert attendance.recorded_at == RECORDED_AT


def test_correct_motivo_demasiado_largo_no_muta() -> None:
    attendance = _record(AttendanceStatus.ATTENDED)

    with pytest.raises(AttendanceReasonRequiredError):
        attendance.correct(
            new_status=AttendanceStatus.NOT_ATTENDED,
            reason="x" * 501,
            actor_id=OTHER_ACTOR_ID,
            occurred_at=CORRECTED_AT,
        )

    assert attendance.status is AttendanceStatus.ATTENDED


def test_correct_motivo_de_500_caracteres_es_valido() -> None:
    attendance = _record(AttendanceStatus.ATTENDED)

    audit = attendance.correct(
        new_status=AttendanceStatus.NOT_ATTENDED,
        reason="x" * 500,
        actor_id=OTHER_ACTOR_ID,
        occurred_at=CORRECTED_AT,
    )

    assert audit is not None
    assert audit.reason == "x" * 500


def test_correct_rechaza_estado_invalido_sin_mutar() -> None:
    attendance = _record(AttendanceStatus.ATTENDED)

    with pytest.raises(AttendanceStatusInvalidError):
        attendance.correct(
            new_status="LATE",  # type: ignore[arg-type]
            reason="Cambio",
            actor_id=OTHER_ACTOR_ID,
            occurred_at=CORRECTED_AT,
        )

    assert attendance.status is AttendanceStatus.ATTENDED


def test_correct_exige_fecha_con_zona_sin_mutar() -> None:
    attendance = _record(AttendanceStatus.ATTENDED)

    with pytest.raises(StaffValidationError) as error:
        attendance.correct(
            new_status=AttendanceStatus.NOT_ATTENDED,
            reason="Cambio",
            actor_id=OTHER_ACTOR_ID,
            occurred_at=datetime(2026, 11, 21, 8, 0),
        )

    assert error.value.code == "staff.audit_invalid"
    assert attendance.status is AttendanceStatus.ATTENDED


# --- AttendanceAudit: invariantes ------------------------------------------


def _recorded_audit() -> AttendanceAudit:
    return AttendanceAudit.recorded(
        assignment_id=ASSIGNMENT_ID,
        new_status=AttendanceStatus.ATTENDED,
        actor_id=ACTOR_ID,
        occurred_at=RECORDED_AT,
    )


def test_recorded_no_admite_valor_anterior() -> None:
    with pytest.raises(StaffValidationError) as error:
        AttendanceAudit(
            assignment_id=ASSIGNMENT_ID,
            action=AttendanceAction.RECORDED,
            new_status=AttendanceStatus.ATTENDED,
            actor_id=ACTOR_ID,
            occurred_at=RECORDED_AT,
            previous_status=AttendanceStatus.NOT_ATTENDED,
        )

    assert error.value.code == "staff.audit_invalid"


def test_recorded_no_admite_motivo() -> None:
    with pytest.raises(StaffValidationError) as error:
        AttendanceAudit(
            assignment_id=ASSIGNMENT_ID,
            action=AttendanceAction.RECORDED,
            new_status=AttendanceStatus.ATTENDED,
            actor_id=ACTOR_ID,
            occurred_at=RECORDED_AT,
            reason="no aplica",
        )

    assert error.value.code == "staff.audit_reason_not_allowed"


def test_corrected_exige_valor_anterior() -> None:
    with pytest.raises(StaffValidationError) as error:
        AttendanceAudit(
            assignment_id=ASSIGNMENT_ID,
            action=AttendanceAction.CORRECTED,
            new_status=AttendanceStatus.ATTENDED,
            actor_id=ACTOR_ID,
            occurred_at=CORRECTED_AT,
            reason="Cambio",
        )

    assert error.value.code == "staff.audit_invalid"


def test_corrected_exige_cambio_de_estado() -> None:
    with pytest.raises(StaffValidationError) as error:
        AttendanceAudit(
            assignment_id=ASSIGNMENT_ID,
            action=AttendanceAction.CORRECTED,
            new_status=AttendanceStatus.ATTENDED,
            actor_id=ACTOR_ID,
            occurred_at=CORRECTED_AT,
            previous_status=AttendanceStatus.ATTENDED,
            reason="Cambio",
        )

    assert error.value.code == "staff.audit_invalid"


@pytest.mark.parametrize("reason", [None, "", "   ", "x" * 501])
def test_corrected_exige_motivo_valido(reason: str | None) -> None:
    with pytest.raises(AttendanceReasonRequiredError) as error:
        AttendanceAudit(
            assignment_id=ASSIGNMENT_ID,
            action=AttendanceAction.CORRECTED,
            new_status=AttendanceStatus.NOT_ATTENDED,
            actor_id=ACTOR_ID,
            occurred_at=CORRECTED_AT,
            previous_status=AttendanceStatus.ATTENDED,
            reason=reason,
        )

    assert error.value.code == ATTENDANCE_REASON_REQUIRED


def test_audit_rechaza_estado_invalido() -> None:
    with pytest.raises(AttendanceStatusInvalidError):
        AttendanceAudit(
            assignment_id=ASSIGNMENT_ID,
            action=AttendanceAction.RECORDED,
            new_status="LATE",  # type: ignore[arg-type]
            actor_id=ACTOR_ID,
            occurred_at=RECORDED_AT,
        )


def test_audit_rechaza_uuids_invalidos() -> None:
    with pytest.raises(StaffValidationError):
        AttendanceAudit.recorded(
            assignment_id="no-uuid",  # type: ignore[arg-type]
            new_status=AttendanceStatus.ATTENDED,
            actor_id=ACTOR_ID,
            occurred_at=RECORDED_AT,
        )
    with pytest.raises(StaffValidationError):
        AttendanceAudit.recorded(
            assignment_id=ASSIGNMENT_ID,
            new_status=AttendanceStatus.ATTENDED,
            actor_id="no-uuid",  # type: ignore[arg-type]
            occurred_at=RECORDED_AT,
        )


def test_audit_occurred_at_debe_incluir_zona() -> None:
    with pytest.raises(StaffValidationError) as error:
        AttendanceAudit.recorded(
            assignment_id=ASSIGNMENT_ID,
            new_status=AttendanceStatus.ATTENDED,
            actor_id=ACTOR_ID,
            occurred_at=datetime(2026, 11, 20, 10, 30),
        )

    assert error.value.code == "staff.audit_invalid"


def test_audit_normaliza_occurred_at_a_utc() -> None:
    lima = timezone(timedelta(hours=-5))
    audit = AttendanceAudit.recorded(
        assignment_id=ASSIGNMENT_ID,
        new_status=AttendanceStatus.ATTENDED,
        actor_id=ACTOR_ID,
        occurred_at=datetime(2026, 11, 20, 5, 30, tzinfo=lima),
    )

    assert audit.occurred_at == RECORDED_AT
    assert audit.occurred_at.tzinfo is UTC


def test_audit_es_inmutable() -> None:
    audit = _recorded_audit()

    with pytest.raises(FrozenInstanceError):
        audit.reason = "cambio"  # type: ignore[misc]


def test_errores_heredan_de_staff_validation_error() -> None:
    assert issubclass(AttendanceStatusInvalidError, StaffValidationError)
    assert issubclass(AttendanceReasonRequiredError, StaffValidationError)


def test_actor_es_uuid_plano_sin_importar_modulos() -> None:
    attendance, audit = Attendance.record(
        assignment_id=uuid4(),
        status=AttendanceStatus.ATTENDED,
        actor_id=uuid4(),
        recorded_at=RECORDED_AT,
    )

    assert isinstance(attendance.assignment_id, UUID)
    assert isinstance(audit.actor_id, UUID)
