"""Horario de una asignación o indisponibilidad, en UTC (AGENTS.md, regla 4).

Se ingresa como fecha y horas de Lima y se guarda como un rango `[inicio, fin)`: terminar a las
18:00 y empezar a las 18:00 no se cruza. Perú no usa horario de verano: Lima es siempre UTC−5
(igual que `commercial`). Python puro: no importa FastAPI, SQLAlchemy ni Pydantic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone

from local_eventos.modules.staff.domain.errors import StaffValidationError

LIMA = timezone(timedelta(hours=-5), "America/Lima")


@dataclass(frozen=True)
class Period:
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("El horario necesita zona horaria.")
        if self.ends_at <= self.starts_at:
            raise StaffValidationError("La hora de fin debe ser distinta de la de inicio.")
        object.__setattr__(self, "starts_at", self.starts_at.astimezone(UTC))
        object.__setattr__(self, "ends_at", self.ends_at.astimezone(UTC))

    @classmethod
    def on(cls, day: date, start: time, end: time) -> Period:
        """Horas de Lima del día indicado. Si `end < start`, termina al día siguiente (R-STF-4)."""
        if start == end:
            raise StaffValidationError("La hora de fin debe ser distinta de la de inicio.")
        end_day = day + timedelta(days=1) if end < start else day
        return cls(
            starts_at=datetime.combine(day, start, LIMA),
            ends_at=datetime.combine(end_day, end, LIMA),
        )

    def overlaps(self, other: Period) -> bool:
        """Intervalos semiabiertos `[inicio, fin)`, igual que la restricción de PostgreSQL."""
        return self.starts_at < other.ends_at and other.starts_at < self.ends_at

    @property
    def local_date(self) -> date:
        return self.starts_at.astimezone(LIMA).date()

    @property
    def local_start(self) -> time:
        return self.starts_at.astimezone(LIMA).time()

    @property
    def local_end(self) -> time:
        return self.ends_at.astimezone(LIMA).time()

    @property
    def ends_next_day(self) -> bool:
        return self.ends_at.astimezone(LIMA).date() > self.local_date

    def describe(self) -> str:
        """Texto para mensajes: "19/12/2026 de 20:00 a 03:00"."""
        return f"{self.local_date:%d/%m/%Y} de {self.local_start:%H:%M} a {self.local_end:%H:%M}"
