"""Pruebas del horario de una asignación (HU17, R-ASG-4/R-COT-1). Sin base de datos."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from local_eventos.modules.staff.domain.assignment_schedule import LIMA, AssignmentSchedule
from local_eventos.modules.staff.domain.errors import (
    AssignmentScheduleInvalidError,
    StaffValidationError,
)


def test_mismo_dia_se_convierte_a_utc() -> None:
    schedule = AssignmentSchedule(
        date=date(2026, 11, 25),
        start_time=time(9, 0),
        end_time=time(17, 0),
    )

    assert schedule.start_at == datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
    assert schedule.end_at == datetime(2026, 11, 25, 22, 0, tzinfo=UTC)
    assert schedule.start_at.tzinfo is UTC
    assert schedule.end_at.tzinfo is UTC


def test_cruce_de_medianoche_termina_al_dia_siguiente() -> None:
    schedule = AssignmentSchedule(
        date=date(2026, 11, 25),
        start_time=time(22, 0),
        end_time=time(2, 0),
    )

    assert schedule.start_at == datetime(2026, 11, 26, 3, 0, tzinfo=UTC)
    assert schedule.end_at == datetime(2026, 11, 26, 7, 0, tzinfo=UTC)
    assert schedule.end_at > schedule.start_at


def test_fin_igual_a_inicio_es_invalido() -> None:
    with pytest.raises(StaffValidationError) as error:
        AssignmentSchedule(
            date=date(2026, 11, 25),
            start_time=time(10, 0),
            end_time=time(10, 0),
        )

    assert isinstance(error.value, AssignmentScheduleInvalidError)
    assert error.value.code == "staff.assignment_schedule_invalid"


def test_el_offset_fijo_de_lima_es_menos_cinco() -> None:
    schedule = AssignmentSchedule(
        date=date(2026, 11, 25),
        start_time=time(0, 0),
        end_time=time(1, 0),
    )

    assert schedule.start_at.utcoffset() == timedelta(0)
    assert schedule.start_at.hour == 5
    assert LIMA.utcoffset(None) == timedelta(hours=-5)


def test_conserva_la_fecha_local_original() -> None:
    schedule = AssignmentSchedule(
        date=date(2026, 12, 31),
        start_time=time(23, 0),
        end_time=time(1, 0),
    )

    assert schedule.date == date(2026, 12, 31)
    assert schedule.start_at.date() == date(2027, 1, 1)
    assert schedule.end_at.date() == date(2027, 1, 1)


def test_horas_con_zona_se_rechazan() -> None:
    with pytest.raises(AssignmentScheduleInvalidError):
        AssignmentSchedule(
            date=date(2026, 11, 25),
            start_time=time(9, 0, tzinfo=UTC),
            end_time=time(17, 0),
        )
