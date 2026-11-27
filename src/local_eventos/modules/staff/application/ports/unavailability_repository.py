"""Puerto del repositorio de indisponibilidades (HU16).

La aplicación usa este contrato y la infraestructura lo implementa. En esta capa
solo hay stdlib y `typing`: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).

`save` persiste la indisponibilidad y su auditoría en la **misma transacción**
(plan §5.5): si la auditoría falla, la indisponibilidad no queda guardada.
Los listados son de solo lectura y no escriben auditoría.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.unavailability_audit import UnavailabilityAudit


class UnavailabilityRepository(Protocol):
    """Operaciones que necesitan los casos de uso de indisponibilidades."""

    async def save(
        self, unavailability: Unavailability, audit: UnavailabilityAudit
    ) -> None:
        """Inserta o actualiza la indisponibilidad junto a su auditoría, en una transacción."""
        ...

    async def get(self, unavailability_id: UUID) -> Unavailability | None:
        """Lee una indisponibilidad por id, sin bloquear."""
        ...

    async def get_for_update(self, unavailability_id: UUID) -> Unavailability | None:
        """Lee una indisponibilidad bloqueando la fila hasta el fin de la transacción.

        Emite `SELECT ... FOR UPDATE` para que dos ediciones/anulaciones no se
        pisen (plan §5.5).
        """
        ...

    async def list_active_overlapping(
        self,
        start_at: datetime,
        end_at: datetime,
        worker_ids: Sequence[UUID],
    ) -> list[Unavailability]:
        """Indisponibilidades `ACTIVE` que se cruzan con `[start_at, end_at)`.

        Filtra por los trabajadores indicados en una sola consulta; usa el mismo
        criterio semiabierto que el solape de asignaciones (plan §2.4).
        """
        ...

    async def list_by_worker(
        self,
        worker_id: UUID,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[Unavailability]:
        """Indisponibilidades de un trabajador, incluidas las `CANCELLED`.

        Con `start_at`/`end_at` opcionales limita el resultado a las que se cruzan
        con esa ventana; sin ellos devuelve todo el historial del trabajador.
        """
        ...
