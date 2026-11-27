"""Pruebas de los esquemas Pydantic de disponibilidad (HU16, plan §4.3).

Cubren la forma del contrato: ventana UTC, horas locales de Lima, motivo
obligatorio, `extra="forbid"`, la serialización con el alias `from` y, sobre
todo, que la respuesta no filtre claves sensibles (pago, tarifa, documento,
teléfono o salario). Las reglas de negocio viven en el dominio/aplicación.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from local_eventos.modules.staff.application.use_cases.get_staff_availability import (
    AvailabilityConflict as AvailabilityConflictView,
)
from local_eventos.modules.staff.application.use_cases.get_staff_availability import (
    AvailabilityItem as AvailabilityItemView,
)
from local_eventos.modules.staff.application.use_cases.get_staff_availability import (
    AvailabilityReport,
)
from local_eventos.modules.staff.application.use_cases.get_staff_availability import (
    UnavailabilityDetail as UnavailabilityDetailView,
)
from local_eventos.modules.staff.domain.enums import (
    AvailabilityState,
    UnavailabilityKind,
    WorkerFunction,
)
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.presentation.availability_schemas import (
    AvailabilityConflict,
    AvailabilityItem,
    AvailabilityOut,
    UnavailabilityCancel,
    UnavailabilityCreate,
    UnavailabilityDetail,
    UnavailabilityListOut,
    UnavailabilityOut,
    UnavailabilityUpdate,
)

WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")
UNAVAILABILITY_ID = UUID("33333333-3333-3333-3333-333333333333")

FORBIDDEN_KEYS = frozenset({"pay", "pay_cents", "tariff", "document", "phone", "salary"})

VALID_CREATE: dict[str, object] = {
    "worker_id": WORKER_ID,
    "date": "2026-12-01",
    "start_time": "08:00:00",
    "end_time": "17:00:00",
    "kind": "VACATION",
}

VALID_UPDATE: dict[str, object] = {
    "kind": "REST",
    "date": "2026-12-01",
    "start_time": "08:00:00",
    "end_time": "17:00:00",
    "reason": "  Cambio de turno  ",
}


def _report() -> AvailabilityReport:
    start_at = datetime(2026, 12, 1, 13, 0, tzinfo=UTC)  # 08:00 en Lima
    end_at = datetime(2026, 12, 1, 22, 0, tzinfo=UTC)  # 17:00 en Lima
    return AvailabilityReport(
        start_at=start_at,
        end_at=end_at,
        items=[
            AvailabilityItemView(
                worker_id=WORKER_ID,
                name="Ana Quispe",
                function=WorkerFunction.WAITER,
                function_description=None,
                state=AvailabilityState.UNAVAILABLE,
                conflicts=(
                    AvailabilityConflictView(
                        event_code="EVT-2026-0012",
                        event_date=date(2026, 12, 1),
                        start_time=time(18, 0),
                        end_time=time(23, 0),
                        function=WorkerFunction.WAITER,
                        function_description=None,
                    ),
                ),
                unavailabilities=(
                    UnavailabilityDetailView(
                        id=UNAVAILABILITY_ID,
                        kind=UnavailabilityKind.VACATION,
                        description=None,
                        start_at=start_at,
                        end_at=end_at,
                    ),
                ),
            )
        ],
    )


def _unavailability() -> Unavailability:
    return Unavailability.register(
        worker_id=WORKER_ID,
        kind=UnavailabilityKind.OTHER,
        description="Trámite personal",
        start_at=datetime(2026, 12, 1, 13, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 1, 22, 0, tzinfo=UTC),
        unavailability_id=UNAVAILABILITY_ID,
    )


def _walk_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_keys(nested)


# --- Consultation -----------------------------------------------------------


def test_availability_out_usa_el_alias_from_y_conserva_utc() -> None:
    schema = AvailabilityOut.from_report(_report())
    data = schema.model_dump(mode="json", by_alias=True)

    assert "from" in data
    assert "from_" not in data
    assert data["from"] == "2026-12-01T13:00:00Z"
    assert data["to"] == "2026-12-01T22:00:00Z"
    assert schema.from_ == schema.from_.astimezone(UTC)


def test_availability_out_normaliza_la_ventana_a_utc() -> None:
    lima = timezone(timedelta(hours=-5))
    report = AvailabilityReport(
        start_at=datetime(2026, 12, 1, 8, 0, tzinfo=lima),
        end_at=datetime(2026, 12, 1, 17, 0, tzinfo=lima),
        items=[],
    )

    data = AvailabilityOut.from_report(report).model_dump(mode="json", by_alias=True)

    assert data["from"] == "2026-12-01T13:00:00Z"
    assert data["to"] == "2026-12-01T22:00:00Z"
    assert data["items"] == []


def test_availability_out_rechaza_instante_sin_zona() -> None:
    with pytest.raises(ValidationError):
        AvailabilityOut.model_validate(
            {"from": "2026-12-01T13:00:00", "to": "2026-12-01T22:00:00Z", "items": []}
        )


def test_availability_item_mapea_estado_conflictos_y_detalles() -> None:
    schema = AvailabilityOut.from_report(_report()).items[0]

    assert schema.worker_id == WORKER_ID
    assert schema.name == "Ana Quispe"
    assert schema.function is WorkerFunction.WAITER
    assert schema.state is AvailabilityState.UNAVAILABLE
    assert schema.conflicts[0].event_code == "EVT-2026-0012"
    assert schema.conflicts[0].start_time == time(18, 0)
    assert schema.unavailabilities[0].id == UNAVAILABILITY_ID
    assert schema.unavailabilities[0].kind is UnavailabilityKind.VACATION


def test_availability_conflict_solo_expone_los_campos_permitidos() -> None:
    assert set(AvailabilityConflict.model_fields) == {
        "event_code",
        "event_date",
        "start_time",
        "end_time",
        "function",
        "function_description",
    }


def test_availability_out_no_incluye_claves_sensibles() -> None:
    data = AvailabilityOut.from_report(_report()).model_dump(mode="json", by_alias=True)
    keys = {key.lower() for key in _walk_keys(data)}

    filtradas = {key for key in keys if any(prohibida in key for prohibida in FORBIDDEN_KEYS)}

    assert filtradas == set()


# --- Indisponibilidad: entrada ---------------------------------------------


def test_unavailability_create_valido_y_horas_locales() -> None:
    payload = UnavailabilityCreate.model_validate(VALID_CREATE)

    assert payload.worker_id == WORKER_ID
    assert payload.date == date(2026, 12, 1)
    assert payload.start_time == time(8, 0)
    assert payload.end_time == time(17, 0)
    assert payload.kind is UnavailabilityKind.VACATION
    assert payload.description is None


def test_unavailability_create_rechaza_claves_extra() -> None:
    with pytest.raises(ValidationError):
        UnavailabilityCreate.model_validate(dict(VALID_CREATE, pay_cents=4500))


def test_unavailability_create_rechaza_hora_con_zona() -> None:
    with pytest.raises(ValidationError):
        UnavailabilityCreate.model_validate(dict(VALID_CREATE, start_time="08:00:00-05:00"))


def test_unavailability_create_descripcion_maximo_120() -> None:
    ok = dict(VALID_CREATE, kind="OTHER", description="x" * 120)
    assert UnavailabilityCreate.model_validate(ok).description == "x" * 120

    with pytest.raises(ValidationError):
        UnavailabilityCreate.model_validate(dict(VALID_CREATE, kind="OTHER", description="x" * 121))


@pytest.mark.parametrize("kind", ["SICK", ""])
def test_unavailability_create_rechaza_kind_invalido(kind: str) -> None:
    with pytest.raises(ValidationError):
        UnavailabilityCreate.model_validate(dict(VALID_CREATE, kind=kind))


def test_unavailability_update_exige_motivo_y_recorta() -> None:
    payload = UnavailabilityUpdate.model_validate(VALID_UPDATE)

    assert payload.reason == "Cambio de turno"
    assert payload.kind is UnavailabilityKind.REST

    with pytest.raises(ValidationError):
        UnavailabilityUpdate.model_validate(
            {k: v for k, v in VALID_UPDATE.items() if k != "reason"}
        )


@pytest.mark.parametrize("reason", ["", "   "])
def test_unavailability_update_rechaza_motivo_vacio(reason: str) -> None:
    with pytest.raises(ValidationError):
        UnavailabilityUpdate.model_validate(dict(VALID_UPDATE, reason=reason))


def test_unavailability_update_rechaza_claves_extra() -> None:
    with pytest.raises(ValidationError):
        UnavailabilityUpdate.model_validate(dict(VALID_UPDATE, worker_id=str(WORKER_ID)))


def test_unavailability_cancel_exige_motivo() -> None:
    with pytest.raises(ValidationError):
        UnavailabilityCancel.model_validate({})
    with pytest.raises(ValidationError):
        UnavailabilityCancel.model_validate({"reason": "   "})

    assert UnavailabilityCancel.model_validate({"reason": "  Error  "}).reason == "Error"


# --- Indisponibilidad: salida ----------------------------------------------


def test_unavailability_out_mapea_fecha_local_y_utc() -> None:
    created = datetime(2026, 11, 27, 15, 0, tzinfo=UTC)
    updated = created + timedelta(hours=1)

    schema = UnavailabilityOut.from_unavailability(
        _unavailability(), created_at=created, updated_at=updated
    )
    data = schema.model_dump(mode="json")

    assert schema.date == date(2026, 12, 1)
    assert schema.start_time == time(8, 0)
    assert schema.end_time == time(17, 0)
    assert schema.start_at == datetime(2026, 12, 1, 13, 0, tzinfo=UTC)
    assert schema.end_at == datetime(2026, 12, 1, 22, 0, tzinfo=UTC)
    assert data["start_at"] == "2026-12-01T13:00:00Z"
    assert data["created_at"] == "2026-11-27T15:00:00Z"
    assert data["status"] == "ACTIVE"
    assert data["kind"] == "OTHER"
    assert data["description"] == "Trámite personal"


def test_unavailability_out_normaliza_metadatos_a_utc() -> None:
    lima = timezone(timedelta(hours=-5))
    schema = UnavailabilityOut.from_unavailability(
        _unavailability(),
        created_at=datetime(2026, 11, 27, 10, 0, tzinfo=lima),
        updated_at=datetime(2026, 11, 27, 11, 0, tzinfo=lima),
    )

    assert schema.created_at == datetime(2026, 11, 27, 15, 0, tzinfo=UTC)
    assert schema.updated_at == datetime(2026, 11, 27, 16, 0, tzinfo=UTC)


def test_unavailability_list_out_serializa_items() -> None:
    out = UnavailabilityOut.from_unavailability(
        _unavailability(),
        created_at=datetime(2026, 11, 27, 15, 0, tzinfo=UTC),
        updated_at=datetime(2026, 11, 27, 15, 0, tzinfo=UTC),
    )

    data = UnavailabilityListOut(items=[out]).model_dump(mode="json")

    assert len(data["items"]) == 1
    assert data["items"][0]["worker_id"] == str(WORKER_ID)


def test_availability_item_rechaza_claves_extra() -> None:
    with pytest.raises(ValidationError):
        AvailabilityItem.model_validate(
            {
                "worker_id": WORKER_ID,
                "name": "Ana",
                "function": None,
                "function_description": None,
                "state": "FREE",
                "conflicts": [],
                "unavailabilities": [],
                "phone": "999999999",
            }
        )


def test_unavailability_detail_rechaza_claves_extra() -> None:
    with pytest.raises(ValidationError):
        UnavailabilityDetail.model_validate(
            {
                "id": UNAVAILABILITY_ID,
                "kind": "REST",
                "description": None,
                "start_at": "2026-12-01T13:00:00Z",
                "end_at": "2026-12-01T22:00:00Z",
                "tariff": 10,
            }
        )
