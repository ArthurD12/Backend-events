"""Pruebas del agregado `Unavailability` y su auditoría (HU16, T-02). Sin base de datos.

Cubre CA-16.1 y CA-16.18 (agregado y auditoría) y CA-16.13/CA-16.14 (semántica
semiabierta y cruce de medianoche en el dominio).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from local_eventos.modules.staff.domain.enums import (
    UnavailabilityKind,
    UnavailabilityStatus,
)
from local_eventos.modules.staff.domain.errors import (
    StaffValidationError,
    UnavailabilityKindRequiredError,
    UnavailabilityReasonRequiredError,
    UnavailabilityScheduleInvalidError,
)
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.unavailability_audit import (
    UnavailabilityAction,
    UnavailabilityAudit,
    UnavailabilitySnapshot,
)

UNAVAILABILITY_ID = UUID("55555555-5555-5555-5555-555555555555")
WORKER_ID = UUID("44444444-4444-4444-4444-444444444444")
ACTOR_ID = UUID("99999999-9999-9999-9999-999999999999")
START_AT = datetime(2026, 12, 1, 14, 0, tzinfo=UTC)
END_AT = datetime(2026, 12, 1, 22, 0, tzinfo=UTC)
OCCURRED_AT = datetime(2026, 11, 27, 10, 30, tzinfo=UTC)


def _register(**overrides: object) -> Unavailability:
    data: dict[str, object] = {
        "worker_id": WORKER_ID,
        "kind": UnavailabilityKind.VACATION,
        "start_at": START_AT,
        "end_at": END_AT,
        "unavailability_id": UNAVAILABILITY_ID,
    }
    data.update(overrides)
    return Unavailability.register(**data)  # type: ignore[arg-type]


def _snapshot(**overrides: object) -> UnavailabilitySnapshot:
    data: dict[str, object] = {
        "kind": UnavailabilityKind.VACATION,
        "description": None,
        "start_at": START_AT,
        "end_at": END_AT,
    }
    data.update(overrides)
    return UnavailabilitySnapshot(**data)  # type: ignore[arg-type]


# --- Agregado: alta (CA-16.1) ---------------------------------------------


def test_ca16_1_alta_nace_activa_con_sus_datos() -> None:
    unavailability = _register()

    assert unavailability.id == UNAVAILABILITY_ID
    assert unavailability.worker_id == WORKER_ID
    assert unavailability.kind is UnavailabilityKind.VACATION
    assert unavailability.description is None
    assert unavailability.start_at == START_AT
    assert unavailability.end_at == END_AT
    assert unavailability.status is UnavailabilityStatus.ACTIVE


def test_ca16_1_alta_registra_actor_y_fecha_hora_utc_en_auditoria() -> None:
    unavailability = _register()
    audit = UnavailabilityAudit.created(
        unavailability_id=unavailability.id,
        actor_id=ACTOR_ID,
        occurred_at=OCCURRED_AT,
    )

    assert audit.action is UnavailabilityAction.CREATED
    assert audit.actor_id == ACTOR_ID
    assert audit.occurred_at == OCCURRED_AT
    assert audit.reason is None
    assert audit.previous_values is None
    assert audit.new_values is None


def test_other_exige_descripcion_normalizada() -> None:
    unavailability = _register(
        kind=UnavailabilityKind.OTHER,
        description="  Cita   médica  ",
    )

    assert unavailability.kind is UnavailabilityKind.OTHER
    assert unavailability.description == "Cita médica"


@pytest.mark.parametrize("description", [None, "", "   "])
def test_other_sin_descripcion_es_invalida(description: str | None) -> None:
    with pytest.raises(StaffValidationError) as error:
        _register(kind=UnavailabilityKind.OTHER, description=description)

    assert error.value.code == "staff.unavailability_description_required"


def test_other_descripcion_de_120_caracteres_es_valida() -> None:
    unavailability = _register(kind=UnavailabilityKind.OTHER, description="x" * 120)

    assert unavailability.description == "x" * 120


def test_other_descripcion_mayor_a_120_es_invalida() -> None:
    with pytest.raises(StaffValidationError) as error:
        _register(kind=UnavailabilityKind.OTHER, description="x" * 121)

    assert error.value.code == "staff.unavailability_description_too_long"


@pytest.mark.parametrize(
    "kind", [UnavailabilityKind.VACATION, UnavailabilityKind.LEAVE, UnavailabilityKind.REST]
)
def test_descripcion_no_permitida_en_otros_tipos(kind: UnavailabilityKind) -> None:
    with pytest.raises(StaffValidationError) as error:
        _register(kind=kind, description="No corresponde")

    assert error.value.code == "staff.unavailability_description_not_allowed"


@pytest.mark.parametrize("kind", [None, "VACATION"])
def test_kind_obligatorio(kind: object) -> None:
    with pytest.raises(UnavailabilityKindRequiredError) as error:
        _register(kind=kind)

    assert error.value.code == "staff.unavailability_kind_required"


@pytest.mark.parametrize(
    ("start_at", "end_at"),
    [
        (START_AT, START_AT),
        (END_AT, START_AT),
        (START_AT, START_AT - timedelta(seconds=1)),
    ],
)
def test_ventana_invalida_por_orden(start_at: datetime, end_at: datetime) -> None:
    with pytest.raises(UnavailabilityScheduleInvalidError):
        _register(start_at=start_at, end_at=end_at)


@pytest.mark.parametrize(
    "naive", [datetime(2026, 12, 1, 14, 0), datetime(2026, 12, 1, 22, 0)]
)
def test_fechas_deben_incluir_zona(naive: datetime) -> None:
    with pytest.raises(UnavailabilityScheduleInvalidError):
        _register(start_at=naive, end_at=END_AT)


def test_normaliza_instantes_a_utc() -> None:
    lima = timezone(timedelta(hours=-5))
    unavailability = _register(
        start_at=datetime(2026, 12, 1, 9, 0, tzinfo=lima),
        end_at=datetime(2026, 12, 1, 17, 0, tzinfo=lima),
    )

    assert unavailability.start_at == START_AT
    assert unavailability.end_at == END_AT
    assert unavailability.start_at.tzinfo is UTC


def test_worker_id_es_inmutable_y_no_hay_delete_ni_reactivacion() -> None:
    unavailability = _register()

    with pytest.raises(AttributeError):
        unavailability.worker_id = uuid4()  # type: ignore[misc]

    assert not hasattr(unavailability, "delete")
    assert not hasattr(unavailability, "activate")
    assert not hasattr(unavailability, "set_worker_id")


def test_worker_id_debe_ser_uuid() -> None:
    with pytest.raises(StaffValidationError) as error:
        _register(worker_id="no-es-uuid")

    assert error.value.code == "staff.unavailability_worker_invalid"


def test_snapshot_tiene_valores_serializables() -> None:
    unavailability = _register(kind=UnavailabilityKind.OTHER, description="Trámite")

    assert unavailability.snapshot() == {
        "kind": "OTHER",
        "description": "Trámite",
        "start_at": START_AT.isoformat(),
        "end_at": END_AT.isoformat(),
    }


# --- Agregado: edición y anulación (CA-16.18) -----------------------------


def test_update_con_cambios_devuelve_true() -> None:
    unavailability = _register()
    new_start = START_AT + timedelta(hours=1)
    new_end = END_AT + timedelta(hours=1)

    changed = unavailability.update(
        kind=UnavailabilityKind.LEAVE,
        start_at=new_start,
        end_at=new_end,
    )

    assert changed is True
    assert unavailability.kind is UnavailabilityKind.LEAVE
    assert unavailability.description is None
    assert unavailability.start_at == new_start
    assert unavailability.end_at == new_end


def test_update_sin_cambios_devuelve_false() -> None:
    unavailability = _register()

    changed = unavailability.update(
        kind=UnavailabilityKind.VACATION,
        start_at=START_AT,
        end_at=END_AT,
    )

    assert changed is False
    assert unavailability.snapshot() == _register().snapshot()


def test_update_invalido_conserva_valores_y_worker() -> None:
    unavailability = _register()

    with pytest.raises(UnavailabilityScheduleInvalidError):
        unavailability.update(
            kind=UnavailabilityKind.LEAVE,
            start_at=START_AT + timedelta(hours=1),
            end_at=START_AT,
        )

    assert unavailability.kind is UnavailabilityKind.VACATION
    assert unavailability.start_at == START_AT
    assert unavailability.end_at == END_AT
    assert unavailability.worker_id == WORKER_ID


def test_update_no_reactiva_una_anulada() -> None:
    unavailability = _register()
    assert unavailability.cancel() is True

    assert unavailability.update(
        kind=UnavailabilityKind.REST,
        start_at=START_AT,
        end_at=END_AT,
    )
    assert unavailability.status is UnavailabilityStatus.CANCELLED


def test_cancel_es_idempotente_y_terminal() -> None:
    unavailability = _register()

    assert unavailability.cancel() is True
    assert unavailability.status is UnavailabilityStatus.CANCELLED
    assert unavailability.cancel() is False
    assert unavailability.status is UnavailabilityStatus.CANCELLED


# --- Agregado: ventana semiabierta (CA-16.13/CA-16.14) --------------------


def test_ca16_13_solo_solapa_dentro_del_intervalo() -> None:
    unavailability = _register()  # [14:00, 22:00)

    assert unavailability.overlaps(START_AT, END_AT) is True
    assert unavailability.overlaps(START_AT - timedelta(hours=2), START_AT) is False
    assert unavailability.overlaps(END_AT, END_AT + timedelta(hours=2)) is False
    assert unavailability.overlaps(START_AT + timedelta(hours=1), START_AT + timedelta(hours=2))
    assert unavailability.overlaps(END_AT - timedelta(minutes=1), END_AT) is True


def test_ca16_14_cruce_de_medianoche_cubre_la_madrugada() -> None:
    start = datetime(2026, 12, 1, 22, 0, tzinfo=UTC)
    end = datetime(2026, 12, 2, 2, 0, tzinfo=UTC)
    unavailability = _register(start_at=start, end_at=end)

    assert unavailability.start_at < unavailability.end_at
    assert unavailability.overlaps(
        datetime(2026, 12, 2, 1, 0, tzinfo=UTC),
        datetime(2026, 12, 2, 3, 0, tzinfo=UTC),
    )
    assert not unavailability.overlaps(
        datetime(2026, 12, 2, 2, 0, tzinfo=UTC),
        datetime(2026, 12, 2, 4, 0, tzinfo=UTC),
    )


def test_ca16_14_intervalos_contiguos_no_solapan() -> None:
    morning = _register(
        start_at=datetime(2026, 12, 1, 8, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 1, 12, 0, tzinfo=UTC),
    )
    afternoon = _register(
        start_at=datetime(2026, 12, 1, 12, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 1, 16, 0, tzinfo=UTC),
    )

    assert morning.overlaps(afternoon.start_at, afternoon.end_at) is False
    assert afternoon.overlaps(morning.start_at, morning.end_at) is False


# --- Auditoría (CA-16.18) -------------------------------------------------


def test_updated_con_motivo_y_snapshots() -> None:
    audit = UnavailabilityAudit.updated(
        unavailability_id=UNAVAILABILITY_ID,
        actor_id=ACTOR_ID,
        occurred_at=OCCURRED_AT,
        reason="  Corrección de horario  ",
        previous_values=_snapshot(),
        new_values=_snapshot(kind=UnavailabilityKind.OTHER, description="Trámite"),
    )

    assert audit.action is UnavailabilityAction.UPDATED
    assert audit.reason == "Corrección de horario"
    assert audit.previous_values == _snapshot()
    assert audit.new_values == _snapshot(
        kind=UnavailabilityKind.OTHER, description="Trámite"
    )


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_updated_sin_motivo_es_invalido(reason: str | None) -> None:
    with pytest.raises(UnavailabilityReasonRequiredError) as error:
        UnavailabilityAudit(
            unavailability_id=UNAVAILABILITY_ID,
            action=UnavailabilityAction.UPDATED,
            actor_id=ACTOR_ID,
            occurred_at=OCCURRED_AT,
            reason=reason,
            previous_values=_snapshot(),
            new_values=_snapshot(),
        )

    assert error.value.code == "staff.unavailability_reason_required"


def test_updated_exige_snapshots() -> None:
    with pytest.raises(StaffValidationError) as error:
        UnavailabilityAudit.updated(
            unavailability_id=UNAVAILABILITY_ID,
            actor_id=ACTOR_ID,
            occurred_at=OCCURRED_AT,
            reason="Cambio",
            previous_values=None,  # type: ignore[arg-type]
            new_values=_snapshot(),
        )

    assert error.value.code == "staff.audit_invalid"


def test_cancelled_con_motivo_y_sin_snapshots() -> None:
    audit = UnavailabilityAudit.cancelled(
        unavailability_id=UNAVAILABILITY_ID,
        actor_id=ACTOR_ID,
        occurred_at=OCCURRED_AT,
        reason="Anulación planificada",
    )

    assert audit.action is UnavailabilityAction.CANCELLED
    assert audit.reason == "Anulación planificada"
    assert audit.previous_values is None
    assert audit.new_values is None


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_cancelled_sin_motivo_es_invalido(reason: str | None) -> None:
    with pytest.raises(UnavailabilityReasonRequiredError) as error:
        UnavailabilityAudit.cancelled(
            unavailability_id=UNAVAILABILITY_ID,
            actor_id=ACTOR_ID,
            occurred_at=OCCURRED_AT,
            reason=reason,  # type: ignore[arg-type]
        )

    assert error.value.code == "staff.unavailability_reason_required"


def test_cancelled_rechaza_snapshots() -> None:
    with pytest.raises(StaffValidationError) as error:
        UnavailabilityAudit(
            unavailability_id=UNAVAILABILITY_ID,
            action=UnavailabilityAction.CANCELLED,
            actor_id=ACTOR_ID,
            occurred_at=OCCURRED_AT,
            reason="Anulada",
            previous_values=_snapshot(),
        )

    assert error.value.code == "staff.audit_invalid"


def test_created_rechaza_motivo_y_snapshots() -> None:
    with pytest.raises(StaffValidationError) as reason_error:
        UnavailabilityAudit(
            unavailability_id=UNAVAILABILITY_ID,
            action=UnavailabilityAction.CREATED,
            actor_id=ACTOR_ID,
            occurred_at=OCCURRED_AT,
            reason="no aplica",
        )
    assert reason_error.value.code == "staff.audit_reason_not_allowed"

    with pytest.raises(StaffValidationError) as snapshot_error:
        UnavailabilityAudit(
            unavailability_id=UNAVAILABILITY_ID,
            action=UnavailabilityAction.CREATED,
            actor_id=ACTOR_ID,
            occurred_at=OCCURRED_AT,
            new_values=_snapshot(),
        )
    assert snapshot_error.value.code == "staff.audit_invalid"


def test_reason_maximo_500_caracteres() -> None:
    audit = UnavailabilityAudit.cancelled(
        unavailability_id=UNAVAILABILITY_ID,
        actor_id=ACTOR_ID,
        occurred_at=OCCURRED_AT,
        reason="x" * 500,
    )
    assert audit.reason == "x" * 500

    with pytest.raises(StaffValidationError) as error:
        UnavailabilityAudit.cancelled(
            unavailability_id=UNAVAILABILITY_ID,
            actor_id=ACTOR_ID,
            occurred_at=OCCURRED_AT,
            reason="x" * 501,
        )
    assert error.value.code == "staff.audit_invalid"


def test_occurred_at_exige_zona_y_normaliza_a_utc() -> None:
    lima = timezone(timedelta(hours=-5))
    audit = UnavailabilityAudit.created(
        unavailability_id=UNAVAILABILITY_ID,
        actor_id=ACTOR_ID,
        occurred_at=datetime(2026, 11, 27, 5, 30, tzinfo=lima),
    )

    assert audit.occurred_at == OCCURRED_AT
    assert audit.occurred_at.tzinfo is UTC

    with pytest.raises(StaffValidationError) as error:
        UnavailabilityAudit.created(
            unavailability_id=UNAVAILABILITY_ID,
            actor_id=ACTOR_ID,
            occurred_at=datetime(2026, 11, 27, 10, 30),
        )
    assert error.value.code == "staff.audit_invalid"


def test_snapshot_round_trip_desde_el_agregado() -> None:
    unavailability = _register(kind=UnavailabilityKind.OTHER, description="Trámite")

    snapshot = UnavailabilitySnapshot.from_mapping(unavailability.snapshot())

    assert snapshot.to_dict() == unavailability.snapshot()
    assert snapshot.kind is UnavailabilityKind.OTHER
    assert snapshot.description == "Trámite"


def test_snapshot_es_inmutable() -> None:
    snapshot = _snapshot()

    with pytest.raises(FrozenInstanceError):
        snapshot.description = "otra"  # type: ignore[misc]


def test_audit_es_inmutable() -> None:
    audit = UnavailabilityAudit.created(
        unavailability_id=UNAVAILABILITY_ID,
        actor_id=ACTOR_ID,
        occurred_at=OCCURRED_AT,
    )

    with pytest.raises(FrozenInstanceError):
        audit.reason = "cambio"  # type: ignore[misc]


def test_no_depende_de_identity_ni_commercial() -> None:
    audit = UnavailabilityAudit.cancelled(
        unavailability_id=UNAVAILABILITY_ID,
        actor_id=uuid4(),
        occurred_at=OCCURRED_AT,
        reason="Anulada",
    )

    assert isinstance(audit.actor_id, UUID)
