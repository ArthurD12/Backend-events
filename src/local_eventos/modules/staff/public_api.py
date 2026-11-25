"""Superficie pública del módulo staff: única vía de uso por otros módulos.

Ningún otro módulo importa las capas internas de `staff`; solo este archivo. Expone
una referencia mínima de solo lectura (`WorkerRef`) y el puerto `WorkerLookup` con
su fábrica `worker_lookup(session)`, más los enums `WorkerFunction`/`WorkerStatus`.

No expone documento, teléfono, tarifa ni operaciones de escritura (AGENTS.md,
regla 3; plan §1.3). HU17 (asignaciones) consultará a los trabajadores solo por aquí.
"""

from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerLookup,
    WorkerRef,
)
from local_eventos.modules.staff.composition import worker_lookup
from local_eventos.modules.staff.domain.enums import (
    WorkerFunction,
    WorkerStatus,
)

__all__ = [
    "WorkerFunction",
    "WorkerLookup",
    "WorkerRef",
    "WorkerStatus",
    "worker_lookup",
]
