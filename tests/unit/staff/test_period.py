"""Horario de asignaciones e indisponibilidades: hora de Lima a UTC y cruces `[inicio, fin)`."""

from datetime import UTC, date, datetime, time

import pytest

from local_eventos.modules.staff.domain.errors import StaffValidationError
from local_eventos.modules.staff.domain.period import Period

DAY = date(2026, 12, 19)


def test_convierte_hora_de_lima_a_utc() -> None:
    period = Period.on(DAY, time(9), time(18))

    assert period.starts_at == datetime(2026, 12, 19, 14, tzinfo=UTC)
    assert period.ends_at == datetime(2026, 12, 19, 23, tzinfo=UTC)
    assert (period.local_date, period.local_start, period.local_end) == (DAY, time(9), time(18))
    assert period.ends_next_day is False


def test_r_stf_4_fin_menor_que_inicio_termina_al_dia_siguiente() -> None:
    period = Period.on(DAY, time(20), time(3))

    assert period.ends_at == datetime(2026, 12, 20, 8, tzinfo=UTC)
    assert period.ends_next_day is True
    assert period.describe() == "19/12/2026 de 20:00 a 03:00"


def test_terminar_a_medianoche_es_el_dia_siguiente() -> None:
    period = Period.on(DAY, time(18), time(0))

    assert period.ends_at == datetime(2026, 12, 20, 5, tzinfo=UTC)


def test_inicio_y_fin_iguales_no_es_un_horario() -> None:
    with pytest.raises(StaffValidationError) as error:
        Period.on(DAY, time(9), time(9))

    assert error.value.code == "staff.validation"


def test_cruces_con_intervalos_semiabiertos() -> None:
    morning = Period.on(DAY, time(8), time(18))

    assert morning.overlaps(Period.on(DAY, time(17), time(23)))
    assert morning.overlaps(Period.on(DAY, time(10), time(11)))
    assert not morning.overlaps(Period.on(DAY, time(18), time(23)))  # se tocan en el borde
    assert not Period.on(DAY, time(18), time(23)).overlaps(morning)
    next_day = Period.on(date(2026, 12, 20), time(2), time(5))
    assert Period.on(DAY, time(20), time(3)).overlaps(next_day)
