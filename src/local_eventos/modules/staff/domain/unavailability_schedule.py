"""Horario local de una indisponibilidad (HU16, R-ASG-4/R-DIS-7).

Recibe la fecha y las horas locales de `America/Lima` del alta o la edición y
expone `start_at`/`end_at` en UTC aware. Aplica las mismas reglas que
`AssignmentSchedule` (R-ASG-4): `end_time == start_time` es inválido y
`end_time < start_time` termina al día siguiente; en otro caso, el mismo día.

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, time, timedelta

from local_eventos.modules.staff.domain.errors import UnavailabilityScheduleInvalidError
from local_eventos.modules.staff.domain.lima import local_to_utc


@dataclass(frozen=True)
class UnavailabilitySchedule:
    """Fecha y horas locales de Lima que se traducen a `start_at`/`end_at` en UTC.

    Attributes:
        date: Fecha local del inicio de la indisponibilidad.
        start_time: Hora local de inicio (sin zona horaria).
        end_time: Hora local de fin (sin zona horaria).
        start_at: Inicio UTC aware, calculado al construir.
        end_at: Fin UTC aware, calculado al construir.
    """

    date: date_type
    start_time: time
    end_time: time
    start_at: datetime = field(init=False)
    end_at: datetime = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.date, date_type) or isinstance(self.date, datetime):
            raise UnavailabilityScheduleInvalidError(
                "La fecha de la indisponibilidad no es válida."
            )
        _validate_time(self.start_time, "inicio")
        _validate_time(self.end_time, "fin")
        if self.start_time == self.end_time:
            raise UnavailabilityScheduleInvalidError(
                "La hora de fin no puede ser igual a la de inicio: "
                "el horario tendría duración cero."
            )

        end_date = self.date + timedelta(days=1) if self.end_time < self.start_time else self.date
        object.__setattr__(self, "start_at", local_to_utc(self.date, self.start_time))
        object.__setattr__(self, "end_at", local_to_utc(end_date, self.end_time))


def _validate_time(value: object, label: str) -> None:
    if not isinstance(value, time) or value.tzinfo is not None:
        raise UnavailabilityScheduleInvalidError(
            f"La hora de {label} debe ser una hora local de America/Lima, sin zona."
        )
