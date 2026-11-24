"""Puerto del repositorio de trabajadores (HU15).

La aplicación usa este contrato y la infraestructura lo implementa. En esta capa
solo hay stdlib y `typing`: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).

`save` persiste la ficha y su auditoría en la **misma transacción** (plan §4): si la
auditoría falla, la ficha no queda guardada.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from local_eventos.modules.staff.domain.audit import WorkerAudit
from local_eventos.modules.staff.domain.document import Document
from local_eventos.modules.staff.domain.enums import (
    WorkerFunction,
    WorkerStatus,
)
from local_eventos.modules.staff.domain.worker import Worker


@dataclass(frozen=True)
class WorkerRef:
    """Referencia mínima del trabajador para otros módulos (CA-15.12).

    No expone documento, teléfono ni tarifa: solo lo que HU17 necesita para
    rechazar inactivos y copiar la función con la que se trabajó.
    """

    id: UUID
    name: str
    function: WorkerFunction | None
    function_description: str | None
    status: WorkerStatus


@dataclass(frozen=True)
class WorkerPage:
    """Una página de trabajadores y el total que cumple el filtro."""

    items: list[Worker]
    total: int
    page: int
    page_size: int


class WorkerRepository(Protocol):
    """Operaciones que necesitan los casos de uso de personal."""

    async def save(self, worker: Worker, audit: WorkerAudit) -> None:
        """Inserta o actualiza la ficha y escribe la auditoría en la misma transacción."""
        ...

    async def get(self, worker_id: UUID) -> Worker | None: ...

    async def get_for_update(self, worker_id: UUID) -> Worker | None:
        """Lee la ficha bloqueando la fila hasta el fin de la transacción (`FOR UPDATE`)."""
        ...

    async def get_by_document(self, document: Document) -> Worker | None:
        """Busca por tipo + número normalizado, incluidos los trabajadores inactivos."""
        ...

    async def search(
        self,
        *,
        text: str,
        function: WorkerFunction | None,
        status: WorkerStatus | None,
        page: int,
        page_size: int,
    ) -> WorkerPage:
        """Página ordenada por nombre; `status=None` incluye activos e inactivos.

        El texto se recorta y compara sin mayúsculas ni tildes contra el nombre
        (`search_text.normalize_name`) o, sin espacios ni guiones, contra el
        documento (`search_text.normalize_document`). `page` es 1-based.
        """
        ...

    async def lookup(self, worker_id: UUID) -> WorkerRef | None:
        """Versión de solo lectura y sin datos sensibles para `staff.public_api`."""
        ...
