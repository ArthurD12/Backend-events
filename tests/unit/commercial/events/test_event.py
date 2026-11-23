"""Entidad Evento (HU10): solo desde contrato firmado y copia de lo contratado."""

from datetime import UTC, date, datetime, time
from uuid import uuid4

import pytest

from local_eventos.modules.commercial.domain.contracts.contract import Contract
from local_eventos.modules.commercial.domain.events.event import (
    Event,
    EventRuleError,
    EventStatus,
    EventValidationError,
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
