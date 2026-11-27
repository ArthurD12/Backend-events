"""Puerto de lectura de la función de una asignación (HU16).

La consulta de disponibilidad recibe los `assignment_id` de una asignación en
conflicto desde el puerto de HU17 (`AssignmentRepository.list_active_overlaps`) y
solo necesita mostrar su función y descripción. Este contrato es **nuevo de HU16**
y no amplía `AssignmentOverlap` ni ningún tipo de HU17 (plan §3.1).

La infraestructura lo implementa con **una sola** consulta `WHERE id IN (...)`
sobre `staff_assignments`, leyendo únicamente `worker_function` y
`function_description`. **Nunca** lee ni expone pago, tarifa, documento ni
teléfono, y no añade predicados de solape: los ids proceden siempre de HU17.
En esta capa solo hay stdlib y `typing` (AGENTS.md, regla 2).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from local_eventos.modules.staff.domain.enums import WorkerFunction


@dataclass(frozen=True)
class AssignmentFunction:
    """Función y descripción de una asignación, sin ningún dato económico.

    Es la única información que HU16 lee de `staff_assignments` para describir un
    conflicto de disponibilidad. `worker_function` puede ser `None` si la fila no
    se encontró (inconsistencia) o si quedó sin función.
    """

    worker_function: WorkerFunction | None
    function_description: str | None


class AssignmentConflictLookup(Protocol):
    """Lectura de solo lectura de la función de asignaciones por id (HU16)."""

    async def by_ids(
        self, assignment_ids: Sequence[UUID]
    ) -> dict[UUID, AssignmentFunction | None]:
        """Devuelve la función por id; los ids ausentes se mapean a `None`.

        Es una única consulta `WHERE id IN (...)`, sin predicados de solape y sin
        pago: HU16 no reimplementa el criterio de HU17.
        """
        ...
