"""Caso de uso: anular lógicamente una indisponibilidad (HU16, T-06, plan §3.4).

Flujo: se bloquea la fila con `get_for_update`; si no existe → 404
`staff.unavailability_not_found`. La anulación es idempotente: si ya está
`CANCELLED` se devuelve sin nueva auditoría (200). En caso contrario el motivo es
obligatorio y no vacío → `staff.unavailability_reason_required` (RN03), se anula
con `cancel()` y se escribe `CANCELLED` con motivo, actor y fecha-hora en la misma
transacción que la entidad (CA-16.18, plan §5.5). No hay borrado físico ni
reactivación (Q4).

Python puro: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from local_eventos.modules.staff.application.errors import UnavailabilityNotFoundError
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.unavailability_repository import (
    UnavailabilityRepository,
)
from local_eventos.modules.staff.domain.enums import UnavailabilityStatus
from local_eventos.modules.staff.domain.errors import UnavailabilityReasonRequiredError
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.unavailability_audit import UnavailabilityAudit

__all__ = ["CancelUnavailability"]


class CancelUnavailability:
    """Anula lógicamente una indisponibilidad y audita el motivo."""

    def __init__(
        self,
        unavailabilities: UnavailabilityRepository,
        clock: Clock | None = None,
    ) -> None:
        self._unavailabilities = unavailabilities
        self._clock = clock

    async def execute(
        self,
        *,
        unavailability_id: UUID,
        reason: str,
        actor_id: UUID,
    ) -> Unavailability:
        """Anula la indisponibilidad y devuelve el agregado persistido.

        Lanza `UnavailabilityNotFoundError` (404) y
        `UnavailabilityReasonRequiredError` (422). Si ya estaba anulada devuelve el
        agregado sin nueva auditoría.
        """
        unavailability = await self._unavailabilities.get_for_update(unavailability_id)
        if unavailability is None:
            raise UnavailabilityNotFoundError()

        if unavailability.status is UnavailabilityStatus.CANCELLED:
            return unavailability

        normalized_reason = _require_reason(reason)

        unavailability.cancel()
        audit = UnavailabilityAudit.cancelled(
            unavailability_id=unavailability.id,
            actor_id=actor_id,
            occurred_at=self._now(),
            reason=normalized_reason,
        )
        await self._unavailabilities.save(unavailability, audit)
        return unavailability

    def _now(self) -> datetime:
        """Instante de auditoría: reloj inyectado o reloj del sistema en UTC."""
        if self._clock is not None:
            return self._clock.now()
        return datetime.now(UTC)


def _require_reason(reason: object) -> str:
    """Exige un motivo no vacío antes de anular (RN03, Q4)."""
    if not isinstance(reason, str) or not reason.strip():
        raise UnavailabilityReasonRequiredError()
    return reason.strip()
