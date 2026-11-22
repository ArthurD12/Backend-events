"""Entidad Cotización: totales, horario, vigencia y estados (HU07, HU08, R-COT-1 a R-COT-5)."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

import pytest

from local_eventos.modules.commercial.domain.quotes.quote import (
    EventDetails,
    EventType,
    LineKind,
    LineUnit,
    Quote,
    QuoteLine,
    QuoteRuleError,
    QuoteStatus,
    QuoteValidationError,
    format_code,
)

TODAY = date(2026, 11, 22)
NOW = datetime(2026, 11, 22, 15, 0, tzinfo=UTC)


def _details(**changes: object) -> EventDetails:
    data: dict[str, object] = {
        "event_type": EventType.WEDDING,
        "event_date": date(2026, 12, 19),
        "start_time": time(20, 0),
        "end_time": time(3, 0),
        "venue": "  Local Los Jardines,   piso 2 ",
        "guests": 120,
        **changes,
    }
    return EventDetails(**data)  # type: ignore[arg-type]


def _buffet(quantity: int = 120, price: int = 4500) -> QuoteLine:
    return QuoteLine(
        kind=LineKind.SERVICE,
        description="Buffet criollo",
        unit=LineUnit.PER_PERSON,
        quantity=quantity,
        unit_price_cents=price,
        service_id=uuid4(),
        catalog_price_cents=4500,
    )


def _transport(amount: int = 15000) -> QuoteLine:
    return QuoteLine(
        kind=LineKind.EXTRA,
        description="Movilidad a Chosica",
        unit=LineUnit.PER_UNIT,
        quantity=1,
        unit_price_cents=amount,
    )


def _quote(**changes: object) -> Quote:
    data: dict[str, object] = {
        "code": "COT-2026-0001",
        "client_id": uuid4(),
        "details": _details(),
        "lines": [_buffet(), _transport()],
        "created_by": uuid4(),
        "now": NOW,
        "today": TODAY,
        **changes,
    }
    return Quote.create(**data)  # type: ignore[arg-type]


def test_ca07_6_se_crea_en_borrador_con_vigencia_de_15_dias() -> None:
    quote = _quote()

    assert quote.status is QuoteStatus.DRAFT
    assert quote.valid_until == TODAY + timedelta(days=15)
    assert quote.details.venue == "Local Los Jardines, piso 2"


def test_ca07_5_subtotales_y_total_se_calculan_solos() -> None:
    quote = _quote()

    assert [line.subtotal_cents for line in quote.lines] == [540_000, 15_000]
    assert quote.total_cents == 555_000


def test_ca07_4_codigo_con_anio_y_correlativo() -> None:
    assert format_code(2026, 7) == "COT-2026-0007"
    assert format_code(2027, 12345) == "COT-2027-12345"


def test_r_cot_1_el_horario_puede_cruzar_medianoche() -> None:
    assert _quote().details.ends_next_day is True
    assert (
        _quote(details=_details(start_time=time(12), end_time=time(17))).details.ends_next_day
        is False
    )


def test_r_cot_1_inicio_y_fin_no_pueden_ser_iguales() -> None:
    with pytest.raises(QuoteValidationError) as error:
        _quote(details=_details(start_time=time(20), end_time=time(20)))
    assert error.value.code == "quote.time_invalid"


def test_r_cot_4_la_fecha_del_evento_no_puede_ser_pasada() -> None:
    _quote(details=_details(event_date=TODAY))
    with pytest.raises(QuoteValidationError) as error:
        _quote(details=_details(event_date=TODAY - timedelta(days=1)))
    assert error.value.code == "quote.event_date_past"


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"guests": 0}, "quote.guests_invalid"),
        ({"venue": "   "}, "quote.venue_required"),
    ],
)
def test_ca07_2_datos_del_evento_obligatorios(changes: dict[str, object], code: str) -> None:
    with pytest.raises(QuoteValidationError) as error:
        _quote(details=_details(**changes))
    assert error.value.code == code


def test_r_cot_5_al_menos_una_linea() -> None:
    with pytest.raises(QuoteValidationError) as error:
        _quote(lines=[])
    assert error.value.code == "quote.lines_required"


@pytest.mark.parametrize(
    ("quantity", "price", "code"),
    [(0, 100, "quote.quantity_invalid"), (1, -1, "quote.price_invalid")],
)
def test_ca07_3_cantidad_y_precio_validos(quantity: int, price: int, code: str) -> None:
    with pytest.raises(QuoteValidationError) as error:
        QuoteLine(
            kind=LineKind.EXTRA,
            description="x",
            unit=LineUnit.PER_UNIT,
            quantity=quantity,
            unit_price_cents=price,
        )
    assert error.value.code == code


def test_ca07_3_concepto_adicional_necesita_descripcion() -> None:
    with pytest.raises(QuoteValidationError) as error:
        QuoteLine(
            kind=LineKind.EXTRA,
            description="  ",
            unit=LineUnit.PER_UNIT,
            quantity=1,
            unit_price_cents=1,
        )
    assert error.value.code == "quote.description_required"


def test_vigencia_no_puede_terminar_antes_de_hoy() -> None:
    with pytest.raises(QuoteValidationError) as error:
        _quote(valid_until=TODAY - timedelta(days=1))
    assert error.value.code == "quote.valid_until_invalid"


def test_ca08_1_en_borrador_se_modifica() -> None:
    quote = _quote()

    quote.update(
        details=_details(guests=150),
        lines=[_buffet(quantity=150, price=4000)],
        valid_until=TODAY + timedelta(days=30),
        today=TODAY,
    )

    assert quote.details.guests == 150
    assert quote.total_cents == 600_000


def test_ca08_1_si_un_dato_falla_no_cambia_nada() -> None:
    quote = _quote()

    with pytest.raises(QuoteValidationError):
        quote.update(
            details=_details(guests=150), lines=[], valid_until=quote.valid_until, today=TODAY
        )

    assert quote.details.guests == 120


@pytest.mark.parametrize(
    "path",
    [
        [QuoteStatus.SENT, QuoteStatus.ACCEPTED],
        [QuoteStatus.SENT, QuoteStatus.REJECTED],
        [QuoteStatus.SENT, QuoteStatus.DRAFT],
        [QuoteStatus.ACCEPTED],
        [QuoteStatus.REJECTED],
    ],
)
def test_r_cot_3_transiciones_permitidas(path: list[QuoteStatus]) -> None:
    quote = _quote()
    for status in path:
        quote.change_status(status, TODAY)
    assert quote.status is path[-1]


@pytest.mark.parametrize("final", [QuoteStatus.ACCEPTED, QuoteStatus.REJECTED])
def test_r_cot_3_aceptada_y_rechazada_son_finales(final: QuoteStatus) -> None:
    quote = _quote()
    quote.change_status(final, TODAY)

    for status in (QuoteStatus.DRAFT, QuoteStatus.SENT, QuoteStatus.ACCEPTED):
        with pytest.raises(QuoteRuleError) as error:
            quote.change_status(status, TODAY)
        assert error.value.code == "quote.invalid_transition"


def test_r_cot_2_enviada_no_se_edita_sin_volver_a_borrador() -> None:
    quote = _quote()
    quote.change_status(QuoteStatus.SENT, TODAY)

    with pytest.raises(QuoteRuleError) as error:
        quote.update(
            details=_details(), lines=[_buffet()], valid_until=quote.valid_until, today=TODAY
        )
    assert error.value.code == "quote.not_editable"

    quote.change_status(QuoteStatus.DRAFT, TODAY)
    quote.update(details=_details(), lines=[_buffet()], valid_until=quote.valid_until, today=TODAY)
    assert len(quote.lines) == 1


@pytest.mark.parametrize("final", [QuoteStatus.ACCEPTED, QuoteStatus.REJECTED])
def test_ca08_4_aceptada_o_rechazada_no_se_modifica(final: QuoteStatus) -> None:
    quote = _quote()
    quote.change_status(final, TODAY)

    with pytest.raises(QuoteRuleError) as error:
        quote.update(
            details=_details(), lines=[_buffet()], valid_until=quote.valid_until, today=TODAY
        )
    assert error.value.code == "quote.not_editable"


def test_ca08_3_vence_si_pasa_la_vigencia_sin_aceptarse() -> None:
    quote = _quote(valid_until=TODAY + timedelta(days=2))
    after = TODAY + timedelta(days=3)

    assert quote.effective_status(TODAY + timedelta(days=2)) is QuoteStatus.DRAFT
    assert quote.effective_status(after) is QuoteStatus.EXPIRED
    with pytest.raises(QuoteRuleError) as error:
        quote.change_status(QuoteStatus.ACCEPTED, after)
    assert error.value.code == "quote.expired"
    with pytest.raises(QuoteRuleError):
        quote.update(details=_details(), lines=[_buffet()], valid_until=after, today=after)


def test_ca08_3_una_aceptada_no_vence() -> None:
    quote = _quote(valid_until=TODAY)
    quote.change_status(QuoteStatus.ACCEPTED, TODAY)

    assert quote.effective_status(TODAY + timedelta(days=30)) is QuoteStatus.ACCEPTED
