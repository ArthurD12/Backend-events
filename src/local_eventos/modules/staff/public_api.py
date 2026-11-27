"""Superficie pública del módulo staff: única vía de uso por otros módulos.

Ningún otro módulo importa las capas internas de `staff`; solo este archivo. Expone
una referencia mínima de solo lectura (`WorkerRef`) y el puerto `WorkerLookup` con
su fábrica `worker_lookup(session)`, más los enums `WorkerFunction`/`WorkerStatus`.
Para HU14 expone `EventAssignment` y el puerto `EventAssignmentLookup` con su
fábrica `event_assignments(session)`.

La consulta pública de asignaciones devuelve solo las **activas** (nombre, función,
descripción e instantes UTC; lista vacía si no hay) y **no** incluye pago, documento,
teléfono ni tarifa; tampoco expone operaciones de escritura (AGENTS.md, regla 3;
plan §1.4, CA-17.21). HU17 (asignaciones) consulta a los trabajadores solo por aquí.
"""

from local_eventos.modules.staff.application.ports.assignment_repository import (
    EventAssignment,
    EventAssignmentLookup,
)
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerLookup,
    WorkerRef,
)
from local_eventos.modules.staff.composition import event_assignments, worker_lookup
from local_eventos.modules.staff.domain.enums import (
    AssignmentStatus,
    WorkerFunction,
    WorkerStatus,
)

__all__ = [
    "AssignmentStatus",
    "EventAssignment",
    "EventAssignmentLookup",
    "WorkerFunction",
    "WorkerLookup",
    "WorkerRef",
    "WorkerStatus",
    "event_assignments",
    "worker_lookup",
]
