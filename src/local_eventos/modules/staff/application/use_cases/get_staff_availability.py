"""Caso de uso: consultar la disponibilidad del personal (HU16, plan §3.1).

Consulta de **solo lectura**. Para cada trabajador activo del filtro calcula el
estado en la ventana pedida reutilizando el criterio de HU17:

1. `WorkerRepository.list_active(function)` devuelve únicamente fichas activas.
2. `UnavailabilityRepository.list_active_overlapping(...)` trae en una sola
   consulta las indisponibilidades que se cruzan con la ventana.
3. Por trabajador se invoca `AssignmentRepository.list_active_overlaps(...)`, el
   mismo puerto que usa HU17; **no** se reimplementa el predicado de solape.
4. Los eventos se resuelven con `commercial.public_api.event_lookup`, cacheando
   por `event_id` dentro de la petición. Un evento `CANCELLED` se descarta sin
   llamar a `release_cancelled`; uno inexistente omite el conflicto con un
   warning de `logging` estándar (no structlog). La consulta nunca escribe.
5. La función de cada asignación en conflicto se lee con **una sola** llamada a
   `AssignmentConflictLookup.by_ids(...)`, nunca desde `AssignmentView`.
6. Precedencia: `UNAVAILABLE` > `BUSY` > `FREE`; se aplican los filtros `state`
   y `function` y se devuelve una lista plana ordenada por nombre.

Python puro: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from uuid import UUID

from local_eventos.modules.commercial.public_api import (
    EventInfo,
    EventLookup,
    EventStatus,
)
from local_eventos.modules.staff.application.ports.assignment_conflict_lookup import (
    AssignmentConflictLookup,
    AssignmentFunction,
)
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentRepository,
)
from local_eventos.modules.staff.application.ports.unavailability_repository import (
    UnavailabilityRepository,
)
from local_eventos.modules.staff.application.ports.worker_repository import WorkerRepository
from local_eventos.modules.staff.domain.availability_query import AvailabilityQuery
from local_eventos.modules.staff.domain.enums import (
    AvailabilityState,
    UnavailabilityKind,
    WorkerFunction,
)
from local_eventos.modules.staff.domain.lima import utc_to_local
from local_eventos.modules.staff.domain.unavailability import Unavailability

_logger = logging.getLogger(__name__)

__all__ = [
    "AvailabilityConflict",
    "AvailabilityItem",
    "AvailabilityReport",
    "GetStaffAvailability",
    "UnavailabilityDetail",
]


@dataclass(frozen=True)
class AvailabilityConflict:
    """Asignación vigente que ocupa parte de la ventana consultada.

    Lleva solo los datos que el administrador necesita para entender el cruce:
    código y fecha del evento, horario local de la asignación y su función. Nunca
    pago, tarifa, documento ni teléfono (CA-16.8, R-DIS-9).
    """

    event_code: str
    event_date: date
    start_time: time
    end_time: time
    function: WorkerFunction | None
    function_description: str | None


@dataclass(frozen=True)
class UnavailabilityDetail:
    """Indisponibilidad activa que explica un estado `UNAVAILABLE` (CA-16.9)."""

    id: UUID
    kind: UnavailabilityKind
    description: str | None
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class AvailabilityItem:
    """Disponibilidad de un trabajador en la ventana consultada.

    `function`/`function_description` son los del trabajador (ficha); los de cada
    conflicto son los de la asignación concreta. `state` ya aplica la precedencia
    `UNAVAILABLE > BUSY > FREE`.
    """

    worker_id: UUID
    name: str
    function: WorkerFunction | None
    function_description: str | None
    state: AvailabilityState
    conflicts: tuple[AvailabilityConflict, ...]
    unavailabilities: tuple[UnavailabilityDetail, ...]


@dataclass(frozen=True)
class AvailabilityReport:
    """Resultado plano de la consulta de disponibilidad, sin paginación."""

    start_at: datetime
    end_at: datetime
    items: list[AvailabilityItem]


@dataclass(frozen=True)
class _Overlap:
    """Solape ya descartado de eventos cancelados o inexistentes, con su evento."""

    worker_id: UUID
    assignment_id: UUID
    event: EventInfo
    start_at: datetime
    end_at: datetime


class GetStaffAvailability:
    """Calcula la disponibilidad del personal sin escribir nada (HU16)."""

    def __init__(
        self,
        workers: WorkerRepository,
        unavailabilities: UnavailabilityRepository,
        assignments: AssignmentRepository,
        events: EventLookup,
        conflicts: AssignmentConflictLookup,
    ) -> None:
        self._workers = workers
        self._unavailabilities = unavailabilities
        self._assignments = assignments
        self._events = events
        self._conflicts = conflicts

    async def execute(self, query: AvailabilityQuery) -> AvailabilityReport:
        """Devuelve el estado de cada trabajador activo que cumple los filtros.

        `AvailabilityQuery` valida la ventana al construirse (horas completas,
        fin posterior al inicio y máximo de 31 días). Repetir la consulta con los
        mismos datos devuelve el mismo resultado: no se guarda, libera ni audita
        nada (CA-16.15, CA-16.16).
        """
        workers = await self._workers.list_active(query.function)
        worker_ids = [worker.id for worker in workers]

        unavailabilities: list[Unavailability] = []
        if worker_ids:
            unavailabilities = await self._unavailabilities.list_active_overlapping(
                query.start_at, query.end_at, worker_ids
            )
        unavailabilities_by_worker = _group_unavailabilities(unavailabilities)

        event_cache: dict[UUID, EventInfo | None] = {}
        overlaps: list[_Overlap] = []
        for worker in workers:
            worker_overlaps = await self._assignments.list_active_overlaps(
                worker.id, query.start_at, query.end_at
            )
            for overlap in worker_overlaps:
                event = await self._resolve_event(overlap.event_id, event_cache)
                if event is None:
                    _logger.warning(
                        "Evento %s no encontrado para la asignación %s del trabajador %s; "
                        "se omite el conflicto de disponibilidad.",
                        overlap.event_id,
                        overlap.id,
                        worker.id,
                        extra={
                            "event_id": str(overlap.event_id),
                            "assignment_id": str(overlap.id),
                            "worker_id": str(worker.id),
                        },
                    )
                    continue
                if event.status is EventStatus.CANCELLED:
                    # Mismo criterio efectivo que HU17, pero sin liberar ni escribir.
                    continue
                overlaps.append(
                    _Overlap(
                        worker_id=worker.id,
                        assignment_id=overlap.id,
                        event=event,
                        start_at=overlap.start_at,
                        end_at=overlap.end_at,
                    )
                )

        functions = await self._functions_by_assignment(overlaps)
        conflicts_by_worker = _group_conflicts(overlaps, functions)

        items: list[AvailabilityItem] = []
        for worker in workers:
            worker_unavailabilities = unavailabilities_by_worker.get(worker.id, ())
            worker_conflicts = conflicts_by_worker.get(worker.id, ())
            state = _state(worker_unavailabilities, worker_conflicts)
            if query.state is not None and state is not query.state:
                continue
            if query.function is not None and worker.function is not query.function:
                continue
            items.append(
                AvailabilityItem(
                    worker_id=worker.id,
                    name=worker.name,
                    function=worker.function,
                    function_description=worker.function_description,
                    state=state,
                    conflicts=worker_conflicts,
                    unavailabilities=tuple(
                        _unavailability_detail(item) for item in worker_unavailabilities
                    ),
                )
            )

        items.sort(key=lambda item: (item.name.casefold(), item.name, str(item.worker_id)))
        return AvailabilityReport(start_at=query.start_at, end_at=query.end_at, items=items)

    async def _resolve_event(
        self, event_id: UUID, cache: dict[UUID, EventInfo | None]
    ) -> EventInfo | None:
        """Resuelve el evento una sola vez por petición, incluido el resultado nulo."""
        if event_id not in cache:
            cache[event_id] = await self._events(event_id)
        return cache[event_id]

    async def _functions_by_assignment(
        self, overlaps: Sequence[_Overlap]
    ) -> dict[UUID, AssignmentFunction | None]:
        """Leo las funciones en una única consulta `by_ids`; sin solapes no hay consulta."""
        assignment_ids = list(dict.fromkeys(overlap.assignment_id for overlap in overlaps))
        if not assignment_ids:
            return {}
        return await self._conflicts.by_ids(assignment_ids)


def _group_unavailabilities(
    unavailabilities: Sequence[Unavailability],
) -> dict[UUID, list[Unavailability]]:
    grouped: dict[UUID, list[Unavailability]] = {}
    for item in unavailabilities:
        grouped.setdefault(item.worker_id, []).append(item)
    for items in grouped.values():
        items.sort(key=lambda item: (item.start_at, str(item.id)))
    return grouped


def _unavailability_detail(item: Unavailability) -> UnavailabilityDetail:
    return UnavailabilityDetail(
        id=item.id,
        kind=item.kind,
        description=item.description,
        start_at=item.start_at,
        end_at=item.end_at,
    )


def _group_conflicts(
    overlaps: Sequence[_Overlap],
    functions: dict[UUID, AssignmentFunction | None],
) -> dict[UUID, tuple[AvailabilityConflict, ...]]:
    grouped: dict[UUID, list[AvailabilityConflict]] = {}
    for overlap in overlaps:
        function = functions.get(overlap.assignment_id)
        grouped.setdefault(overlap.worker_id, []).append(
            AvailabilityConflict(
                event_code=overlap.event.code,
                event_date=overlap.event.event_date,
                start_time=utc_to_local(overlap.start_at).time(),
                end_time=utc_to_local(overlap.end_at).time(),
                function=None if function is None else function.worker_function,
                function_description=(None if function is None else function.function_description),
            )
        )
    result: dict[UUID, tuple[AvailabilityConflict, ...]] = {}
    for worker_id, conflicts in grouped.items():
        conflicts.sort(
            key=lambda conflict: (
                conflict.event_date,
                conflict.start_time,
                conflict.event_code,
            )
        )
        result[worker_id] = tuple(conflicts)
    return result


def _state(
    unavailabilities: Sequence[Unavailability],
    conflicts: Sequence[AvailabilityConflict],
) -> AvailabilityState:
    if unavailabilities:
        return AvailabilityState.UNAVAILABLE
    if conflicts:
        return AvailabilityState.BUSY
    return AvailabilityState.FREE
