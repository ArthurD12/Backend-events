"""Disponibilidad de un trabajador para un horario (CA-16.4)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.period import Period
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.worker import Worker


class AvailabilityStatus(StrEnum):
    FREE = "FREE"
    BUSY = "BUSY"  # tiene una asignación vigente que se cruza
    UNAVAILABLE = "UNAVAILABLE"  # avisó que no puede


@dataclass(frozen=True)
class Availability:
    worker: Worker
    status: AvailabilityStatus
    event_code: str | None = None  # solo si está ocupado
    period: Period | None = None  # el horario con el que se cruza

    @classmethod
    def of(
        cls,
        worker: Worker,
        period: Period,
        assignments: Iterable[Assignment],
        unavailability: Iterable[Unavailability],
    ) -> Availability:
        """Ocupado gana a no disponible (CA-16.4). Solo cuentan las asignaciones vigentes."""
        busy = next(
            (
                a
                for a in sorted(assignments, key=lambda a: a.period.starts_at)
                if a.worker_id == worker.id and a.is_active and a.period.overlaps(period)
            ),
            None,
        )
        if busy is not None:
            return cls(worker, AvailabilityStatus.BUSY, busy.event_code, busy.period)
        away = next(
            (
                u
                for u in sorted(unavailability, key=lambda u: u.period.starts_at)
                if u.worker_id == worker.id and u.period.overlaps(period)
            ),
            None,
        )
        if away is not None:
            return cls(worker, AvailabilityStatus.UNAVAILABLE, period=away.period)
        return cls(worker, AvailabilityStatus.FREE)
