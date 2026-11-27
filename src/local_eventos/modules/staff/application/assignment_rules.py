"""Reglas compartidas por los casos de uso de asignaciones (HU17).

Reúne la validación de la fecha contra el evento (Q5) y la descripción de los
solapes, para que `RegisterAssignment` y `UpdateAssignment` apliquen exactamente
las mismas reglas sin duplicarlas. Solo usa el dominio y la frontera permitida con
`commercial.public_api` (R-ASG-13); no importa FastAPI, SQLAlchemy ni Pydantic
(AGENTS.md, regla 2).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date as date_type
from datetime import time, timedelta

from local_eventos.modules.commercial.public_api import EventLookup
from local_eventos.modules.staff.application.errors import AssignmentConflict
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentOverlap,
)
from local_eventos.modules.staff.domain.errors import AssignmentDateInvalidError


def validate_event_date(
    *,
    assignment_date: date_type,
    event_date: date_type,
    event_start_time: time,
    event_end_time: time,
) -> None:
    """Aplica Q5 comparando solo fechas locales, nunca instantes.

    La fecha debe ser la del evento o, si el evento cruza la medianoche, también la
    del día siguiente (plan §2.2 y §10.2).
    """
    allowed = {event_date}
    if event_end_time < event_start_time:
        allowed.add(event_date + timedelta(days=1))
    if assignment_date not in allowed:
        raise AssignmentDateInvalidError()


async def describe_conflicts(
    event_lookup: EventLookup, overlaps: Sequence[AssignmentOverlap]
) -> tuple[AssignmentConflict, ...]:
    """Traduce solapes a conflictos con código, fecha y horario del evento.

    Nunca expone documento, teléfono, tarifa ni pago (CA-17.10); un evento que ya
    no existe se omite del detalle.
    """
    conflicts: list[AssignmentConflict] = []
    for overlap in overlaps:
        event = await event_lookup(overlap.event_id)
        if event is None:
            continue
        conflicts.append(
            AssignmentConflict(
                event_code=event.code,
                event_date=event.event_date,
                start_time=event.start_time,
                end_time=event.end_time,
            )
        )
    return tuple(conflicts)


__all__ = ["describe_conflicts", "validate_event_date"]
