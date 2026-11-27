"""Pruebas de la ventana de consulta y del horario de indisponibilidad (HU16, T-03).

Cubre CA-16.14 (cruce de medianoche), CA-16.20 (máximo 31 días corridos) y los
bordes de la ventana semiabierta. Sin base de datos.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from local_eventos.modules.staff.domain.availability_query import AvailabilityQuery
from local_eventos.modules.staff.domain.enums import AvailabilityState, WorkerFunction
from local_eventos.modules.staff.domain.errors import (
    AvailabilityRangeTooLargeError,
    AvailabilityWindowInvalidError,
    UnavailabilityScheduleInvalidError,
)
from local_eventos.modules.staff.domain.unavailability_schedule import UnavailabilitySchedule


def test_dia_completo_va_de_medianoche_a_medianoche_siguiente() -> None:
    query = AvailabilityQuery(from_date=date(2026, 12, 1), to_date=date(2026, 12, 1))

    assert query.start_at == datetime(2026, 12, 1, 5, 0, tzinfo=UTC)
    assert query.end_at == datetime(2026, 12, 2, 5, 0, tzinfo=UTC)
    assert query.start_at.tzinfo is UTC
    assert query.end_at.tzinfo is UTC


def test_dia_completo_en_rango_multi_dia() -> None:
    query = AvailabilityQuery(from_date=date(2026, 12, 1), to_date=date(2026, 12, 3))

    assert query.start_at == datetime(2026, 12, 1, 5, 0, tzinfo=UTC)
    assert query.end_at == datetime(2026, 12, 4, 5, 0, tzinfo=UTC)


def test_horas_en_el_mismo_dia() -> None:
    query = AvailabilityQuery(
        from_date=date(2026, 12, 1),
        to_date=date(2026, 12, 1),
        start_time=time(18, 0),
        end_time=time(23, 0),
    )

    assert query.start_at == datetime(2026, 12, 1, 23, 0, tzinfo=UTC)
    assert query.end_at == datetime(2026, 12, 2, 4, 0, tzinfo=UTC)


def test_ca16_14_cruce_de_medianoche_en_un_solo_dia() -> None:
    query = AvailabilityQuery(
        from_date=date(2026, 12, 1),
        to_date=date(2026, 12, 1),
        start_time=time(22, 0),
        end_time=time(2, 0),
    )

    assert query.start_at == datetime(2026, 12, 2, 3, 0, tzinfo=UTC)
    assert query.end_at == datetime(2026, 12, 2, 7, 0, tzinfo=UTC)
    assert query.end_at > query.start_at


def test_en_rango_multi_dia_la_hora_de_fin_se_aplica_al_to_date() -> None:
    query = AvailabilityQuery(
        from_date=date(2026, 12, 1),
        to_date=date(2026, 12, 3),
        start_time=time(18, 0),
        end_time=time(23, 0),
    )

    assert query.start_at == datetime(2026, 12, 1, 23, 0, tzinfo=UTC)
    assert query.end_at == datetime(2026, 12, 4, 4, 0, tzinfo=UTC)


def test_ventana_es_semiabierta_en_el_limite() -> None:
    query = AvailabilityQuery(
        from_date=date(2026, 12, 1),
        to_date=date(2026, 12, 1),
        start_time=time(10, 0),
        end_time=time(12, 0),
    )

    assert query.start_at <= datetime(2026, 12, 1, 15, 0, tzinfo=UTC) < query.end_at
    assert not datetime(2026, 12, 1, 17, 0, tzinfo=UTC) < query.end_at


@pytest.mark.parametrize(
    ("start_time", "end_time"),
    [(time(10, 0), None), (None, time(12, 0))],
)
def test_una_sola_hora_es_invalida(start_time: time | None, end_time: time | None) -> None:
    with pytest.raises(AvailabilityWindowInvalidError) as error:
        AvailabilityQuery(
            from_date=date(2026, 12, 1),
            to_date=date(2026, 12, 1),
            start_time=start_time,
            end_time=end_time,
        )

    assert error.value.code == "staff.availability_window_invalid"


def test_horas_iguales_en_un_solo_dia_son_invalidas() -> None:
    with pytest.raises(AvailabilityWindowInvalidError):
        AvailabilityQuery(
            from_date=date(2026, 12, 1),
            to_date=date(2026, 12, 1),
            start_time=time(10, 0),
            end_time=time(10, 0),
        )


def test_horas_con_zona_se_rechazan() -> None:
    with pytest.raises(AvailabilityWindowInvalidError):
        AvailabilityQuery(
            from_date=date(2026, 12, 1),
            to_date=date(2026, 12, 1),
            start_time=time(10, 0, tzinfo=UTC),
            end_time=time(12, 0),
        )


def test_from_date_posterior_a_to_date_es_invalida() -> None:
    with pytest.raises(AvailabilityWindowInvalidError):
        AvailabilityQuery(from_date=date(2026, 12, 2), to_date=date(2026, 12, 1))


def test_una_fecha_datetime_no_es_una_fecha_local() -> None:
    with pytest.raises(AvailabilityWindowInvalidError):
        AvailabilityQuery(
            from_date=datetime(2026, 12, 1, tzinfo=UTC),  # type: ignore[arg-type]
            to_date=date(2026, 12, 1),
        )


def test_ca16_20_31_dias_corridos_inclusive_es_valido() -> None:
    query = AvailabilityQuery(from_date=date(2026, 12, 1), to_date=date(2026, 12, 31))

    assert query.start_at == datetime(2026, 12, 1, 5, 0, tzinfo=UTC)
    assert query.end_at == datetime(2027, 1, 1, 5, 0, tzinfo=UTC)


def test_ca16_20_32_dias_corridos_es_demasiado_largo() -> None:
    with pytest.raises(AvailabilityRangeTooLargeError) as error:
        AvailabilityQuery(from_date=date(2026, 12, 1), to_date=date(2027, 1, 1))

    assert error.value.code == "staff.availability_range_too_large"


def test_filtros_opcionales_de_funcion_y_estado() -> None:
    query = AvailabilityQuery(
        from_date=date(2026, 12, 1),
        to_date=date(2026, 12, 1),
        function=WorkerFunction.WAITER,
        state=AvailabilityState.BUSY,
    )

    assert query.function is WorkerFunction.WAITER
    assert query.state is AvailabilityState.BUSY


def test_funcion_invalida_se_rechaza() -> None:
    with pytest.raises(AvailabilityWindowInvalidError):
        AvailabilityQuery(
            from_date=date(2026, 12, 1),
            to_date=date(2026, 12, 1),
            function="WAITER",  # type: ignore[arg-type]
        )


def test_unavailability_schedule_mismo_dia_se_convierte_a_utc() -> None:
    schedule = UnavailabilitySchedule(
        date=date(2026, 12, 1),
        start_time=time(9, 0),
        end_time=time(17, 0),
    )

    assert schedule.start_at == datetime(2026, 12, 1, 14, 0, tzinfo=UTC)
    assert schedule.end_at == datetime(2026, 12, 1, 22, 0, tzinfo=UTC)


def test_ca16_14_unavailability_schedule_cruce_de_medianoche() -> None:
    schedule = UnavailabilitySchedule(
        date=date(2026, 12, 1),
        start_time=time(22, 0),
        end_time=time(2, 0),
    )

    assert schedule.start_at == datetime(2026, 12, 2, 3, 0, tzinfo=UTC)
    assert schedule.end_at == datetime(2026, 12, 2, 7, 0, tzinfo=UTC)


def test_unavailability_schedule_fin_igual_a_inicio_es_invalido() -> None:
    with pytest.raises(UnavailabilityScheduleInvalidError) as error:
        UnavailabilitySchedule(
            date=date(2026, 12, 1),
            start_time=time(10, 0),
            end_time=time(10, 0),
        )

    assert error.value.code == "staff.unavailability_schedule_invalid"
