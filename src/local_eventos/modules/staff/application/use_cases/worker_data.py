"""Datos editables de un trabajador (HU15).

DTO compartido por `RegisterWorker` y `UpdateWorker`: representa la ficha que
llega desde presentación ya tipada con los value objects del dominio. Python
puro: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass

from local_eventos.modules.staff.domain.document import WorkerDocumentType
from local_eventos.modules.staff.domain.enums import WorkerFunction, WorkerType
from local_eventos.modules.staff.domain.money import Money


@dataclass(frozen=True)
class WorkerData:
    """Campos editables de la ficha de un trabajador (plan §5.2)."""

    name: str
    document_type: WorkerDocumentType
    document_number: str
    phone: str | None = None
    function: WorkerFunction | None = None
    function_description: str | None = None
    worker_type: WorkerType | None = None
    rate: Money | None = None
    overtime_applies: bool = False
    overtime_rate: Money | None = None
