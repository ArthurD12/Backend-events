"""Horario de una asignación de personal (HU17, R-ASG-4/R-COT-1).

Recibe fecha y horas locales de `America/Lima` y expone el inicio y el fin en UTC
aware. Perú no aplica horario de verano: se usa el offset fijo `-05:00`, como el resto
del proyecto. El value object no conoce eventos; comparar la fecha con la del evento
es responsabilidad del caso de uso.

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta, timezone
from datetime import date as date_type

from local_eventos.modules.staff.domain.errors import AssignmentScheduleInvalidError

LIMA = timezone(timedelta(hours=-5), "America/Lima")


@dataclass(frozen=True)
class AssignmentSchedule:
    """Fecha y horas locales que se traducen a `start_at`/`end_at` en UTC.

    Si `end_time` es menor que `start_time` la asignación termina al día siguiente
    (R-COT-1); si son iguales, el horario es inválido porque su duración sería cero.
    """

    date: date_type
    start_time: time
    end_time: time
    start_at: datetime = field(init=False)
    end_at: datetime = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.date, date_type) or isinstance(self.date, datetime):
            raise AssignmentScheduleInvalidError("La fecha de la asignación no es válida.")
        self._validate_time(self.start_time, "inicio")
        self._validate_time(self.end_time, "fin")
        if self.start_time == self.end_time:
            raise AssignmentScheduleInvalidError(
                "La hora de fin no puede ser igual a la de inicio: "
                "el horario tendría duración cero."
            )

        end_date = self.date + timedelta(days=1) if self.end_time < self.start_time else self.date
        start_at = datetime.combine(self.date, self.start_time, tzinfo=LIMA).astimezone(UTC)
        end_at = datetime.combine(end_date, self.end_time, tzinfo=LIMA).astimezone(UTC)
        object.__setattr__(self, "start_at", start_at)
        object.__setattr__(self, "end_at", end_at)

    @staticmethod
    def _validate_time(value: object, label: str) -> None:
        if not isinstance(value, time) or value.tzinfo is not None:
            raise AssignmentScheduleInvalidError(
                f"La hora de {label} debe ser una hora local de America/Lima, sin zona."
            )
