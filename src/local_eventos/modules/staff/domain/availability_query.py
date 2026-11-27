"""Value object de la ventana de consulta de disponibilidad (HU16, R-DIS-7).

Traduce una entrada local de `America/Lima` (offset fijo `-05:00`) a una ventana
UTC semiabierta `[start_at, end_at)`. Sin horas se consulta el día completo; con
horas, el fin se aplica al `to_date` y, si el rango es de un solo día y la hora de
fin es menor que la de inicio, termina al día siguiente (R-ASG-4). Se admiten como
mucho 31 días corridos, ambos incluidos (CA-16.20).

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from local_eventos.modules.staff.domain.enums import AvailabilityState, WorkerFunction
from local_eventos.modules.staff.domain.errors import (
    AvailabilityRangeTooLargeError,
    AvailabilityWindowInvalidError,
)
from local_eventos.modules.staff.domain.lima import local_to_utc

_MAX_DAYS = 31


@dataclass(frozen=True)
class AvailabilityQuery:
    """Ventana de consulta y filtros opcionales de disponibilidad.

    Attributes:
        from_date: Primer día local (Lima) de la consulta.
        to_date: Último día local (Lima) de la consulta; no puede ir antes de `from_date`.
        start_time: Hora local de inicio; obligatoria junto con `end_time`.
        end_time: Hora local de fin; obligatoria junto con `start_time`.
        function: Filtro opcional por función del trabajador.
        state: Filtro opcional por estado de disponibilidad.
        start_at: Inicio UTC aware de la ventana, calculado al construir.
        end_at: Fin UTC aware (exclusivo) de la ventana, calculado al construir.
    """

    from_date: date
    to_date: date
    start_time: time | None = None
    end_time: time | None = None
    function: WorkerFunction | None = None
    state: AvailabilityState | None = None
    start_at: datetime = field(init=False)
    end_at: datetime = field(init=False)

    def __post_init__(self) -> None:
        _require_date(self.from_date, "inicio")
        _require_date(self.to_date, "fin")
        if self.to_date < self.from_date:
            raise AvailabilityWindowInvalidError(
                "La fecha de fin no puede ser anterior a la de inicio."
            )
        if (self.to_date - self.from_date).days > _MAX_DAYS - 1:
            raise AvailabilityRangeTooLargeError()

        start_at, end_at = self._window()
        if end_at <= start_at:
            raise AvailabilityWindowInvalidError(
                "La ventana de consulta debe terminar después de empezar."
            )
        object.__setattr__(self, "start_at", start_at)
        object.__setattr__(self, "end_at", end_at)

        _require_optional_type(self.function, WorkerFunction, "La función no es válida.")
        _require_optional_type(self.state, AvailabilityState, "El estado no es válido.")

    def _window(self) -> tuple[datetime, datetime]:
        if (self.start_time is None) != (self.end_time is None):
            raise AvailabilityWindowInvalidError(
                "Debe indicar ambas horas o ninguna para consultar el día completo."
            )
        if self.start_time is None or self.end_time is None:
            start_date = self.from_date
            end_date = self.to_date + timedelta(days=1)
            return (
                local_to_utc(start_date, time(0, 0)),
                local_to_utc(end_date, time(0, 0)),
            )

        _require_time(self.start_time, "inicio")
        _require_time(self.end_time, "fin")

        end_date = self.to_date
        if self.from_date == self.to_date:
            if self.start_time == self.end_time:
                raise AvailabilityWindowInvalidError(
                    "La hora de fin no puede ser igual a la de inicio: "
                    "la ventana tendría duración cero."
                )
            if self.end_time < self.start_time:
                end_date += timedelta(days=1)

        return (
            local_to_utc(self.from_date, self.start_time),
            local_to_utc(end_date, self.end_time),
        )


def _require_date(value: object, label: str) -> None:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise AvailabilityWindowInvalidError(f"La fecha de {label} de la ventana no es válida.")


def _require_time(value: object, label: str) -> None:
    if not isinstance(value, time) or value.tzinfo is not None:
        raise AvailabilityWindowInvalidError(
            f"La hora de {label} debe ser una hora local de America/Lima, sin zona."
        )


def _require_optional_type[T](value: T | None, expected: type[T], message: str) -> None:
    if value is not None and not isinstance(value, expected):
        raise AvailabilityWindowInvalidError(message)
