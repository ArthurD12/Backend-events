"""Puerto del repositorio de asignaciones (HU17).

La aplicación usa este contrato y la infraestructura lo implementa. En esta capa
solo hay stdlib y `typing`: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
El único import externo es `EventStatus` por `commercial.public_api`, la frontera
permitida entre módulos (R-ASG-13).

`save` persiste la asignación y su auditoría en la **misma transacción** (plan §5.5):
si la auditoría falla, la asignación no queda. La liberación de un evento cancelado
no escribe auditoría: es un dato derivado (`occupies=false`, plan §2.4).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from local_eventos.modules.commercial.public_api import EventStatus
from local_eventos.modules.staff.domain.assignment import Assignment
from local_eventos.modules.staff.domain.assignment_audit import AssignmentAudit
from local_eventos.modules.staff.domain.enums import AssignmentStatus, WorkerFunction


@dataclass(frozen=True)
class AssignmentView:
    """Vista de lectura de una asignación con el nombre del trabajador y del evento.

    El pago se incluye porque la lectura con `staff:manage` lo devuelve (decisión
    del PO, 25/11/2026); la consulta pública de HU14 usa `EventAssignment`, que no
    lo expone. `start_at`/`end_at` están en UTC aware.
    """

    id: UUID
    event_id: UUID
    worker_id: UUID
    worker_name: str
    function: WorkerFunction
    function_description: str | None
    start_at: datetime
    end_at: datetime
    pay_cents: int
    currency: str
    status: AssignmentStatus
    event_code: str
    event_status: EventStatus


@dataclass(frozen=True)
class AssignmentOverlap:
    """Asignación que se cruza con un horario candidato.

    Solo lleva lo necesario para detectar y describir el cruce; el caso de uso
    completa código, fecha y horario del evento consultando `commercial.public_api`.
    """

    id: UUID
    event_id: UUID
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class EventAssignment:
    """Asignación activa de un evento para la ficha de HU14, sin pago.

    Es la superficie que `staff.public_api` expondrá a `reporting`: nombre del
    trabajador, función, descripción e instantes UTC. No incluye pago, documento,
    teléfono ni tarifa (CA-17.21, plan §1.4).
    """

    worker_id: UUID
    worker_name: str
    function: WorkerFunction
    function_description: str | None
    starts_at: datetime
    ends_at: datetime


class AssignmentRepository(Protocol):
    """Operaciones que necesitan los casos de uso de asignaciones."""

    async def lock_worker(self, worker_id: UUID) -> None:
        """Bloquea la fila de `staff_workers` hasta el fin de la transacción.

        Serializa altas, ediciones, anulaciones y la baja del mismo trabajador; el
        orden de bloqueo es siempre trabajador → asignación (plan §5.5).
        """
        ...

    async def save(self, assignment: Assignment, audit: AssignmentAudit) -> None:
        """Inserta o actualiza la asignación y escribe la auditoría en la misma transacción."""
        ...

    async def get(self, assignment_id: UUID) -> Assignment | None: ...

    async def get_for_update(self, assignment_id: UUID) -> Assignment | None:
        """Lee la asignación bloqueando la fila hasta el fin de la transacción (`FOR UPDATE`)."""
        ...

    async def list_active_overlaps(
        self,
        worker_id: UUID,
        start_at: datetime,
        end_at: datetime,
        *,
        exclude_assignment_id: UUID | None = None,
    ) -> list[AssignmentOverlap]:
        """Asignaciones activas que ocupan y se cruzan con `[start_at, end_at)`.

        `exclude_assignment_id` permite validar una edición sin contar la propia
        asignación. No incluye asignaciones liberadas (`occupies=false`).
        """
        ...

    async def list_by_event(self, event_id: UUID) -> list[AssignmentView]:
        """Asignaciones `ACTIVE` del evento, ordenadas por `start_at` (incluye pago)."""
        ...

    async def list_occupying(self, worker_id: UUID) -> list[Assignment]:
        """Asignaciones `ACTIVE` que ocupan (`occupies=true`), para liberar cancelados."""
        ...

    async def release(self, assignments: Sequence[Assignment]) -> None:
        """Marca `occupies=false` sin cambiar estado ni escribir auditoría (R-ASG-12)."""
        ...

    async def has_active_ending_after(self, worker_id: UUID, moment: datetime) -> bool:
        """Indica si hay una asignación `ACTIVE` que ocupa y termina tras `moment`."""
        ...

    async def get_view(self, assignment_id: UUID) -> AssignmentView | None:
        """Vista de una asignación por id, incluidas las anuladas (plan §3.4)."""
        ...
