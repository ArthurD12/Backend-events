"""Caso de uso: listar indisponibilidades para el administrador (HU16, §3.5).

Consulta de solo lectura que filtra por trabajador y, opcionalmente, por una
ventana local de Lima. La ventana usa las mismas reglas que `AvailabilityQuery`
sin horas: día completo, fechas completas y como máximo 31 días corridos
(`staff.availability_range_too_large`). Incluye las indisponibilidades
`CANCELLED` para que el administrador recupere los identificadores al editar o
anular. No escribe ni audita.

Python puro: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, time, timedelta
from uuid import UUID

from local_eventos.modules.staff.application.ports.unavailability_repository import (
    UnavailabilityRepository,
)
from local_eventos.modules.staff.domain.errors import (
    AvailabilityRangeTooLargeError,
    AvailabilityWindowInvalidError,
)
from local_eventos.modules.staff.domain.lima import local_to_utc
from local_eventos.modules.staff.domain.unavailability import Unavailability

_MAX_DAYS = 31

__all__ = ["ListUnavailability"]


class ListUnavailability:
    """Lista indisponibilidades (incluidas `CANCELLED`) sin escribir nada."""

    def __init__(self, unavailabilities: UnavailabilityRepository) -> None:
        self._unavailabilities = unavailabilities

    async def execute(
        self,
        *,
        worker_id: UUID | None = None,
        from_date: date_type | None = None,
        to_date: date_type | None = None,
    ) -> list[Unavailability]:
        """Devuelve las indisponibilidades que cumplen los filtros opcionales.

        Lanza `AvailabilityWindowInvalidError` (422) si se envía una sola fecha y
        `AvailabilityRangeTooLargeError` (422) si la ventana supera 31 días
        corridos (CA-16.20).
        """
        start_at, end_at = _window(from_date, to_date)
        if worker_id is not None:
            return await self._unavailabilities.list_by_worker(worker_id, start_at, end_at)
        return await self._unavailabilities.list(start_at=start_at, end_at=end_at)


def _window(
    from_date: date_type | None, to_date: date_type | None
) -> tuple[datetime | None, datetime | None]:
    """Traduce las fechas locales (día completo) a la ventana UTC de filtro."""
    if (from_date is None) != (to_date is None):
        raise AvailabilityWindowInvalidError(
            "Debe indicar ambas fechas o ninguna para filtrar por ventana."
        )
    if from_date is None or to_date is None:
        return None, None
    if not isinstance(from_date, date_type) or isinstance(from_date, datetime):
        raise AvailabilityWindowInvalidError("La fecha de inicio del filtro no es válida.")
    if not isinstance(to_date, date_type) or isinstance(to_date, datetime):
        raise AvailabilityWindowInvalidError("La fecha de fin del filtro no es válida.")
    if to_date < from_date:
        raise AvailabilityWindowInvalidError(
            "La fecha de fin no puede ser anterior a la de inicio."
        )
    if (to_date - from_date).days > _MAX_DAYS - 1:
        raise AvailabilityRangeTooLargeError()

    start_at = local_to_utc(from_date, time(0, 0))
    end_at = local_to_utc(to_date + timedelta(days=1), time(0, 0))
    return start_at, end_at
