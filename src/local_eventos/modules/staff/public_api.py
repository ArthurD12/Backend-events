"""Superficie pública del módulo staff: única vía de uso por otros módulos.

HU17 (asignaciones) consultará a los trabajadores solo por aquí: recibe una
referencia mínima de solo lectura con id, nombre, función, descripción y estado.
No se exponen documento, teléfono, tarifa ni operaciones de escritura (AGENTS.md,
regla 3; plan §1.3).
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
