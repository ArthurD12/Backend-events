"""Caso de uso: editar una indisponibilidad existente (HU16, T-06, plan §3.3).

Flujo: se bloquea la fila con `get_for_update`; si no existe → 404
`staff.unavailability_not_found`. Una indisponibilidad `CANCELLED` es terminal y
no admite edición → 409 `staff.unavailability_cancelled` (Q4). El motivo es
obligatorio y no vacío → `staff.unavailability_reason_required` (RN03).

Los nuevos datos se validan como en el alta: `UnavailabilitySchedule` convierte
fecha y horas locales de Lima a una ventana UTC semiabierta (R-ASG-4) y el
agregado valida tipo, descripción y `start_at < end_at`. Si no hay cambios reales
se devuelve el agregado sin escribir auditoría (idempotente); si los hay, se
escribe `UPDATED` con motivo y los snapshots anterior/nuevo en la **misma
transacción** que la entidad (CA-16.18, plan §5.5).

Python puro: sin FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from datetime import date as date_type
from uuid import UUID

from local_eventos.modules.staff.application.errors import (
    UnavailabilityCancelledError,
    UnavailabilityNotFoundError,
)
from local_eventos.modules.staff.application.ports.clock import Clock
from local_eventos.modules.staff.application.ports.unavailability_repository import (
    UnavailabilityRepository,
)
from local_eventos.modules.staff.domain.enums import (
    UnavailabilityKind,
    UnavailabilityStatus,
)
from local_eventos.modules.staff.domain.errors import UnavailabilityReasonRequiredError
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.unavailability_audit import (
    UnavailabilityAudit,
    UnavailabilitySnapshot,
)
from local_eventos.modules.staff.domain.unavailability_schedule import (
    UnavailabilitySchedule,
)

__all__ = ["UpdateUnavailability"]


class UpdateUnavailability:
    """Edita tipo, descripción y ventana de una indisponibilidad, auditando el cambio."""

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
        date: date_type,
        start_time: time,
        end_time: time,
        kind: UnavailabilityKind | None,
        description: str | None,
        reason: str,
        actor_id: UUID,
    ) -> Unavailability:
        """Edita la indisponibilidad y devuelve el agregado persistido.

        Lanza `UnavailabilityNotFoundError` (404), `UnavailabilityCancelledError`
        (409), `UnavailabilityReasonRequiredError` (422) antes de mutar y las
        validaciones del alta (`staff.unavailability_schedule_invalid`,
        `staff.unavailability_kind_required`, `staff.unavailability_description_*`,
        422). Un no-op devuelve el agregado sin auditoría.
        """
        unavailability = await self._unavailabilities.get_for_update(unavailability_id)
        if unavailability is None:
            raise UnavailabilityNotFoundError()
        if unavailability.status is UnavailabilityStatus.CANCELLED:
            raise UnavailabilityCancelledError()

        normalized_reason = _require_reason(reason)

        schedule = UnavailabilitySchedule(
            date=date,
            start_time=start_time,
            end_time=end_time,
        )
        previous = UnavailabilitySnapshot.from_mapping(unavailability.snapshot())
        changed = unavailability.update(
            kind=kind,
            description=description,
            start_at=schedule.start_at,
            end_at=schedule.end_at,
        )
        if not changed:
            return unavailability

        new = UnavailabilitySnapshot.from_mapping(unavailability.snapshot())
        audit = UnavailabilityAudit.updated(
            unavailability_id=unavailability.id,
            actor_id=actor_id,
            occurred_at=self._now(),
            reason=normalized_reason,
            previous_values=previous,
            new_values=new,
        )
        await self._unavailabilities.save(unavailability, audit)
        return unavailability

    def _now(self) -> datetime:
        """Instante de auditoría: reloj inyectado o reloj del sistema en UTC."""
        if self._clock is not None:
            return self._clock.now()
        return datetime.now(UTC)


def _require_reason(reason: object) -> str:
    """Exige un motivo no vacío antes de mutar (RN03, Q4)."""
    if not isinstance(reason, str) or not reason.strip():
        raise UnavailabilityReasonRequiredError()
    return reason.strip()
