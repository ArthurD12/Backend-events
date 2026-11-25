"""Periodo en que un trabajador avisó que no puede trabajar (CA-16.1).

Es un aviso, no una operación con historial: se puede quitar (plan, §4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from local_eventos.modules.staff.domain.errors import StaffValidationError
from local_eventos.modules.staff.domain.period import Period

REASON_MAX_LENGTH = 200


@dataclass(frozen=True)
class Unavailability:
    id: UUID
    worker_id: UUID
    period: Period
    reason: str | None
    created_by: UUID
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        worker_id: UUID,
        period: Period,
        reason: str | None,
        created_by: UUID,
        now: datetime,
    ) -> Unavailability:
        return cls(
            id=uuid4(),
            worker_id=worker_id,
            period=period,
            reason=clean_reason(reason),
            created_by=created_by,
            created_at=now,
        )


def clean_reason(reason: str | None) -> str | None:
    """Motivo opcional, sin espacios de más y con un máximo de caracteres."""
    cleaned = " ".join((reason or "").split()) or None
    if cleaned and len(cleaned) > REASON_MAX_LENGTH:
        raise StaffValidationError(f"El motivo no puede superar {REASON_MAX_LENGTH} caracteres.")
    return cleaned
