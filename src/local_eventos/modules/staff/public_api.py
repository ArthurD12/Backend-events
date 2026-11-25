"""Superficie pública del módulo staff: única vía de uso por otros módulos.

`commercial` libera aquí al personal de un evento cancelado (R-STF-5), dentro de la misma
transacción de la petición: si algo falla, no queda ni el evento cancelado ni las asignaciones
retiradas.
"""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.staff import composition
from local_eventos.modules.staff.application.use_cases.assignments import (
    ReleaseEventAssignments,
)


class AssignmentReleaser(Protocol):
    """Retira las asignaciones vigentes de un evento y devuelve cuántas eran."""

    async def __call__(self, event_id: UUID, *, released_by: UUID, now: datetime) -> int: ...


def assignment_releaser(session: AsyncSession) -> AssignmentReleaser:
    return ReleaseEventAssignments(composition.assignment_repository(session))


__all__ = ["AssignmentReleaser", "assignment_releaser"]
