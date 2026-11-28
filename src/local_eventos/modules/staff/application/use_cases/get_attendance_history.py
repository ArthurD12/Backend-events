"""Caso de uso: historial de asistencia de un trabajador (HU18, T-04, plan §3.2).

Flujo:

1. Valida `page >= 1`, `1 <= page_size <= 100` y, si vienen ambas, `from <= to`;
   cualquier fallo → 422 `staff.attendance_date_range_invalid`.
2. `worker_lookup.get(worker_id)`; si no existe → 404 `staff.worker_not_found`.
   Un trabajador inactivo **sí** conserva historial (R-ATT-16/CA-18.14).
3. `list_history` devuelve una fila por asignación `ACTIVE` o `CANCELLED`, ya
   ordenada por `start_at DESC`; el filtro `event_id` se aplica en SQL.
4. Los eventos se resuelven con `commercial.public_api.event_lookup`
   **deduplicando por `event_id`** y de forma tolerante: si un evento es huérfano
   la fila se conserva con `event=None` (campos `null`), sin 404 ni descarte
   (R-ATT-23/CA-18.22).
5. El filtro de fecha del evento se aplica en memoria sobre `event_date`. Las
   filas con evento huérfano (sin `event_date`) se excluyen cuando hay `from`/`to`
   y se incluyen sin filtro de fecha o cuando el filtro es por `event_id`.
6. `total` se calcula sobre las filas filtradas y después se recorta la página
   (página fuera de rango → `items=[]` con el total correcto).

No resuelve nombres de usuario: eso es responsabilidad de presentación
(`identity.public_api.user_names`). Python puro: sin FastAPI, SQLAlchemy ni
Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from local_eventos.modules.commercial.public_api import EventInfo, EventLookup
from local_eventos.modules.staff.application.attendance_errors import (
    AttendanceDateRangeInvalidError,
    AttendanceWorkerNotFoundError,
)
from local_eventos.modules.staff.application.ports.attendance_repository import (
    AttendanceHistoryRow,
    AttendanceRepository,
)
from local_eventos.modules.staff.application.ports.worker_repository import WorkerLookup

MAX_PAGE_SIZE = 100

__all__ = [
    "AttendanceHistoryItem",
    "AttendanceHistoryPage",
    "GetAttendanceHistory",
    "MAX_PAGE_SIZE",
]


@dataclass(frozen=True)
class AttendanceHistoryItem:
    """Fila del historial con su evento resuelto (`None` si es huérfano)."""

    row: AttendanceHistoryRow
    event: EventInfo | None


@dataclass(frozen=True)
class AttendanceHistoryPage:
    """Página del historial y el total de filas que cumplen los filtros."""

    items: list[AttendanceHistoryItem]
    total: int
    page: int
    page_size: int


class GetAttendanceHistory:
    """Consulta el historial de asistencia de un trabajador, incluidas anuladas."""

    def __init__(
        self,
        attendance: AttendanceRepository,
        workers: WorkerLookup,
        event_lookup: EventLookup,
    ) -> None:
        self._attendance = attendance
        self._workers = workers
        self._event_lookup = event_lookup

    async def execute(
        self,
        *,
        worker_id: UUID,
        from_: date | None = None,
        to_: date | None = None,
        event_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AttendanceHistoryPage:
        """Devuelve la página del historial con el total tras aplicar los filtros.

        Lanza `AttendanceDateRangeInvalidError` (422) si la paginación o el rango
        de fechas no son válidos y `AttendanceWorkerNotFoundError` (404) si el
        trabajador no existe.
        """
        _validate(page=page, page_size=page_size, from_=from_, to_=to_)

        worker = await self._workers.get(worker_id)
        if worker is None:
            raise AttendanceWorkerNotFoundError()

        rows = await self._attendance.list_history(worker_id, event_id)

        events: dict[UUID, EventInfo | None] = {}
        for row in rows:
            if row.event_id not in events:
                events[row.event_id] = await self._event_lookup(row.event_id)

        filtered = _filter_by_event_date(rows, events, from_=from_, to_=to_)

        total = len(filtered)
        start = (page - 1) * page_size
        page_rows = filtered[start : start + page_size]
        items = [AttendanceHistoryItem(row=row, event=events[row.event_id]) for row in page_rows]
        return AttendanceHistoryPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )


def _validate(
    *,
    page: int,
    page_size: int,
    from_: date | None,
    to_: date | None,
) -> None:
    if page < 1:
        raise AttendanceDateRangeInvalidError("El número de página debe ser mayor o igual a 1.")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise AttendanceDateRangeInvalidError(
            f"El tamaño de página debe estar entre 1 y {MAX_PAGE_SIZE}."
        )
    if from_ is not None and to_ is not None and from_ > to_:
        raise AttendanceDateRangeInvalidError(
            "La fecha inicial del filtro no puede ser posterior a la final."
        )


def _filter_by_event_date(
    rows: list[AttendanceHistoryRow],
    events: dict[UUID, EventInfo | None],
    *,
    from_: date | None,
    to_: date | None,
) -> list[AttendanceHistoryRow]:
    """Aplica `[from, to]` inclusivo; sin filtro de fecha conserva las huérfanas."""
    if from_ is None and to_ is None:
        return list(rows)

    filtered: list[AttendanceHistoryRow] = []
    for row in rows:
        event = events[row.event_id]
        if event is None:
            # Sin `event_date` no puede coincidir con un rango de fechas (CA-18.22).
            continue
        if from_ is not None and event.event_date < from_:
            continue
        if to_ is not None and event.event_date > to_:
            continue
        filtered.append(row)
    return filtered
