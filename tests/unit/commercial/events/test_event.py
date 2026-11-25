"""Entidad Evento (HU10): solo desde contrato firmado y copia de lo contratado."""

from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID, uuid4

import pytest

from local_eventos.modules.commercial.domain.contracts.contract import Contract
from local_eventos.modules.commercial.domain.events.event import (
    Event,
    EventAction,
    EventRuleError,
    EventStatus,
    EventValidationError,
    FieldChange,
    PlanningWarning,
    format_event_code,
)
from local_eventos.modules.commercial.domain.quotes.quote import (
    EventDetails,
    EventType,
    LineKind,
    LineUnit,
    Quote,
    QuoteLine,
    QuoteStatus,
)

TODAY = date(2026, 11, 22)
NOW = datetime(2026, 11, 22, 15, tzinfo=UTC)


def _accepted_quote() -> Quote:
    quote = Quote.create(
        code="COT-2026-0001",
        client_id=uuid4(),
        details=EventDetails(
            event_type=EventType.WEDDING,
            event_date=date(2026, 12, 19),
            start_time=time(20),
            end_time=time(3),
            venue="Local Los Jardines",
            guests=120,
        ),  # fmt: skip
        lines=[
            QuoteLine(
                kind=LineKind.SERVICE,
                description="Buffet criollo",
                unit=LineUnit.PER_PERSON,
                quantity=120,
                unit_price_cents=4000,
                service_id=uuid4(),
                catalog_price_cents=4500,
            ),  # fmt: skip
            QuoteLine(
                kind=LineKind.EXTRA,
                description="Movilidad",
                unit=LineUnit.PER_UNIT,
                quantity=1,
                unit_price_cents=15000,
            ),  # fmt: skip
        ],
        created_by=uuid4(),
        now=NOW,
        today=TODAY,
    )
    quote.change_status(QuoteStatus.ACCEPTED, TODAY)
    return quote


def _contract(quote: Quote, *, signed: bool = True) -> Contract:
    contract = Contract.generate(
        code="CON-2026-0001", quote=quote, today=TODAY, created_by=uuid4(), now=NOW
    )
    if signed:
        contract.sign(
            signed_on=TODAY, signer_name="José", advance_payment_id=uuid4(),
            recorded_by=uuid4(), now=NOW, today=TODAY,
        )  # fmt: skip
    return contract


def test_ca10_2_copia_lo_contratado_y_nace_programado() -> None:
    quote = _accepted_quote()
    contract = _contract(quote)
    coordinator = uuid4()

    event = Event.from_contract(
        code="EVT-2026-0001", contract=contract, quote=quote, coordinator_id=coordinator,
        created_by=uuid4(), now=NOW,
    )  # fmt: skip

    assert event.status is EventStatus.SCHEDULED
    assert (event.contract_id, event.quote_id, event.client_id) == (
        contract.id,
        quote.id,
        quote.client_id,
    )
    assert (event.event_date, event.start_time, event.end_time) == (
        date(2026, 12, 19),
        time(20),
        time(3),
    )
    assert event.ends_next_day is True
    assert (event.venue, event.guests, event.coordinator_id) == (
        "Local Los Jardines",
        120,
        coordinator,
    )
    assert [(s.description, s.quantity) for s in event.services] == [
        ("Buffet criollo", 120),
        ("Movilidad", 1),
    ]


def test_ca10_1_solo_contrato_firmado_con_adelanto() -> None:
    quote = _accepted_quote()

    with pytest.raises(EventRuleError) as error:
        Event.from_contract(
            code="EVT-2026-0001", contract=_contract(quote, signed=False), quote=quote,
            coordinator_id=uuid4(), created_by=uuid4(), now=NOW,
        )  # fmt: skip
    assert error.value.code == "event.contract_not_ready"


def test_ca10_3_codigo() -> None:
    assert format_event_code(2026, 12) == "EVT-2026-0012"


def _scheduled_event() -> Event:
    quote = _accepted_quote()
    return Event.from_contract(
        code="EVT-2026-0001", contract=_contract(quote), quote=quote, coordinator_id=uuid4(),
        created_by=uuid4(), now=NOW,
    )  # fmt: skip


def test_ca11_c1_cancela_con_motivo_y_auditoria() -> None:
    event = _scheduled_event()
    user = uuid4()

    event.cancel(reason="  El cliente   canceló ", cancelled_by=user, now=NOW)

    assert event.status is EventStatus.CANCELLED
    assert event.cancellation is not None
    assert (event.cancellation.reason, event.cancellation.cancelled_by) == (
        "El cliente canceló",
        user,
    )
    assert event.cancellation.cancelled_at == NOW


@pytest.mark.parametrize(
    ("reason", "code"), [(" ", "event.reason_required"), ("x" * 501, "event.reason_too_long")]
)
def test_ca11_c2_motivo_obligatorio(reason: str, code: str) -> None:
    event = _scheduled_event()

    with pytest.raises(EventValidationError) as error:
        event.cancel(reason=reason, cancelled_by=uuid4(), now=NOW)

    assert error.value.code == code
    assert event.status is EventStatus.SCHEDULED


@pytest.mark.parametrize(
    "status", [EventStatus.IN_PROGRESS, EventStatus.FINISHED, EventStatus.CANCELLED]
)
def test_r_evt_5_solo_programado_o_confirmado(status: EventStatus) -> None:
    event = _scheduled_event()
    event.status = status

    with pytest.raises(EventRuleError) as error:
        event.cancel(reason="Canceló", cancelled_by=uuid4(), now=NOW)

    assert error.value.code == "event.not_cancellable"


def test_r_evt_5_confirmado_se_cancela() -> None:
    event = _scheduled_event()
    event.status = EventStatus.CONFIRMED

    event.cancel(reason="Canceló", cancelled_by=uuid4(), now=NOW)

    assert event.status is EventStatus.CANCELLED


def test_ca11_c5_cancelar_deja_su_cambio() -> None:
    event = _scheduled_event()
    user = uuid4()

    change = event.cancel(reason="Canceló", cancelled_by=user, now=NOW)

    assert (change.action, change.changed_by, change.changed_at) == (
        EventAction.CANCELLED,
        user,
        NOW,
    )
    assert change.fields == (FieldChange("status", "SCHEDULED", "CANCELLED"),)


# --- HU11: planificación y estados ---


def _planning(event: Event, **changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "event_date": event.event_date,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "venue": event.venue,
        "guests": event.guests,
        "coordinator_id": event.coordinator_id,
    }
    return values | changes


def _update(event: Event, by: UUID | None = None, **changes: Any) -> Any:
    return event.update_planning(
        **_planning(event, **changes), by=by or uuid4(), now=NOW, today=TODAY
    )


def test_ca11_2_edita_y_guarda_antes_y_despues() -> None:
    event = _scheduled_event()
    user, coordinator = uuid4(), uuid4()
    old_coordinator = event.coordinator_id

    change = _update(event, by=user, venue="  Local   El Olivar ", guests=150,
                     coordinator_id=coordinator)  # fmt: skip

    assert (event.venue, event.guests, event.coordinator_id) == (
        "Local El Olivar",
        150,
        coordinator,
    )
    assert change is not None
    assert (change.action, change.changed_by, change.changed_at) == (
        EventAction.PLANNING_UPDATED,
        user,
        NOW,
    )
    assert change.fields == (
        FieldChange("venue", "Local Los Jardines", "Local El Olivar"),
        FieldChange("guests", 120, 150),
        FieldChange("coordinator_id", str(old_coordinator), str(coordinator)),
    )
    assert change.warnings == ()


def test_r_evt_7_editar_no_toca_los_servicios() -> None:
    event = _scheduled_event()
    services = event.services

    _update(event, guests=200)

    assert event.services == services


def test_sin_cambios_no_hay_historial() -> None:
    event = _scheduled_event()

    assert _update(event, venue=" Local Los Jardines ") is None


@pytest.mark.parametrize(
    "changes",
    [
        {"event_date": date(2026, 12, 20)},
        {"start_time": time(19)},
        {"end_time": time(4)},
    ],
)
def test_r_evt_9_avisa_si_cambia_fecha_u_horario(changes: dict[str, Any]) -> None:
    event = _scheduled_event()

    change = _update(event, **changes)

    assert change is not None
    assert change.warnings == (PlanningWarning.STAFF_MAY_NEED_REVIEW,)


def test_r_cot_1_horario_puede_cruzar_la_medianoche() -> None:
    event = _scheduled_event()

    _update(event, start_time=time(22), end_time=time(1))

    assert event.ends_next_day is True


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"event_date": date(2026, 11, 21)}, "event.date_past"),
        ({"start_time": time(20), "end_time": time(20)}, "event.time_invalid"),
        ({"guests": 0}, "event.guests_invalid"),
        ({"guests": 10_001}, "event.guests_invalid"),
        ({"venue": "  "}, "event.venue_required"),
        ({"venue": "x" * 301}, "event.venue_too_long"),
    ],
)
def test_ca11_2_campos_invalidos(changes: dict[str, Any], code: str) -> None:
    event = _scheduled_event()

    with pytest.raises(EventValidationError) as error:
        _update(event, **changes)

    assert error.value.code == code
    assert (event.guests, event.venue) == (120, "Local Los Jardines")


def test_r_cot_4_hoy_es_valido() -> None:
    event = _scheduled_event()

    assert _update(event, event_date=TODAY) is not None


@pytest.mark.parametrize("status", [EventStatus.SCHEDULED, EventStatus.CONFIRMED])
def test_r_evt_6_se_edita_en_programado_y_confirmado(status: EventStatus) -> None:
    event = _scheduled_event()
    event.status = status

    assert _update(event, guests=90) is not None


@pytest.mark.parametrize(
    "status", [EventStatus.IN_PROGRESS, EventStatus.FINISHED, EventStatus.CANCELLED]
)
def test_r_evt_6_no_se_edita_en_otros_estados(status: EventStatus) -> None:
    event = _scheduled_event()
    event.status = status

    with pytest.raises(EventRuleError) as error:
        _update(event, guests=90)

    assert error.value.code == "event.not_editable"


def test_ca11_4_avanza_un_estado_a_la_vez() -> None:
    event = _scheduled_event()
    user = uuid4()

    confirmed = event.confirm(by=user, now=NOW)
    started = event.start(by=user, now=NOW, today=event.event_date)
    finished = event.finish(by=user, now=NOW)

    assert event.status is EventStatus.FINISHED
    assert [c.action for c in (confirmed, started, finished)] == [
        EventAction.CONFIRMED,
        EventAction.STARTED,
        EventAction.FINISHED,
    ]
    assert [c.fields for c in (confirmed, started, finished)] == [
        (FieldChange("status", "SCHEDULED", "CONFIRMED"),),
        (FieldChange("status", "CONFIRMED", "IN_PROGRESS"),),
        (FieldChange("status", "IN_PROGRESS", "FINISHED"),),
    ]
    assert all(c.changed_by == user and c.changed_at == NOW for c in (confirmed, finished))


@pytest.mark.parametrize(
    ("status", "action"),
    [
        (EventStatus.SCHEDULED, "start"),
        (EventStatus.SCHEDULED, "finish"),
        (EventStatus.CONFIRMED, "confirm"),
        (EventStatus.CONFIRMED, "finish"),
        (EventStatus.IN_PROGRESS, "confirm"),
        (EventStatus.IN_PROGRESS, "start"),
        (EventStatus.FINISHED, "confirm"),
        (EventStatus.FINISHED, "start"),
        (EventStatus.FINISHED, "finish"),
        (EventStatus.CANCELLED, "confirm"),
        (EventStatus.CANCELLED, "start"),
        (EventStatus.CANCELLED, "finish"),
    ],
)
def test_ca11_4_transiciones_prohibidas(status: EventStatus, action: str) -> None:
    event = _scheduled_event()
    event.status = status
    calls = {
        "confirm": lambda: event.confirm(by=uuid4(), now=NOW),
        "start": lambda: event.start(by=uuid4(), now=NOW, today=event.event_date),
        "finish": lambda: event.finish(by=uuid4(), now=NOW),
    }

    with pytest.raises(EventRuleError) as error:
        calls[action]()

    assert error.value.code == "event.invalid_transition"
    assert event.status is status


@pytest.mark.parametrize(
    ("today", "end", "allowed"),
    [
        (date(2026, 12, 19), time(3), True),
        (date(2026, 12, 20), time(3), True),  # cruza la medianoche (R-COT-1)
        (date(2026, 12, 20), time(23), False),
        (date(2026, 12, 18), time(3), False),
        (date(2026, 12, 21), time(3), False),
    ],
)
def test_r_evt_8_en_ejecucion_solo_el_dia_del_evento(today: date, end: time, allowed: bool) -> None:
    event = _scheduled_event()  # 19/12/2026, desde las 20:00
    event.end_time = end
    event.confirm(by=uuid4(), now=NOW)

    if allowed:
        event.start(by=uuid4(), now=NOW, today=today)
        assert event.status is EventStatus.IN_PROGRESS
    else:
        with pytest.raises(EventRuleError) as error:
            event.start(by=uuid4(), now=NOW, today=today)
        assert error.value.code == "event.not_event_day"
        assert event.status is EventStatus.CONFIRMED
