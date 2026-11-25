"""Asignación de un trabajador a un evento (HU17).

No se borra: se retira y queda quién y cuándo (CA-17.7). Solo una asignación vigente bloquea el
horario del trabajador (RN12); la base de datos lo garantiza con una restricción de exclusión.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from local_eventos.modules.staff.domain.errors import StaffRuleError
from local_eventos.modules.staff.domain.period import Period
from local_eventos.modules.staff.domain.unavailability import clean_reason
from local_eventos.modules.staff.domain.worker import WorkerFunction, check_cents

EVENT_CANCELLED_REASON = "Evento cancelado"  # R-STF-5


class AssignmentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    WITHDRAWN = "WITHDRAWN"


@dataclass(frozen=True)
class AssignmentWithdrawal:
    reason: str | None
    withdrawn_by: UUID
    withdrawn_at: datetime


@dataclass
class Assignment:
    id: UUID
    worker_id: UUID
    event_id: UUID
    event_code: str  # copia: el código del evento no cambia
    function: WorkerFunction
    period: Period
    agreed_pay_cents: int
    status: AssignmentStatus
    created_by: UUID
    created_at: datetime
    withdrawal: AssignmentWithdrawal | None = None

    @classmethod
    def create(
        cls,
        *,
        worker_id: UUID,
        event_id: UUID,
        event_code: str,
        function: WorkerFunction,
        period: Period,
        agreed_pay_cents: int,
        created_by: UUID,
        now: datetime,
    ) -> Assignment:
        """CA-17.2. Los cruces y el estado del trabajador y del evento los revisa aplicación."""
        return cls(
            id=uuid4(),
            worker_id=worker_id,
            event_id=event_id,
            event_code=event_code,
            function=function,
            period=period,
            agreed_pay_cents=check_cents(agreed_pay_cents, "El pago acordado"),  # R-STF-3
            status=AssignmentStatus.ACTIVE,
            created_by=created_by,
            created_at=now,
        )

    @property
    def is_active(self) -> bool:
        return self.status is AssignmentStatus.ACTIVE

    def withdraw(self, *, reason: str | None, withdrawn_by: UUID, now: datetime) -> None:
        """CA-17.7: deja de bloquear el horario; queda el motivo, quién y cuándo."""
        if not self.is_active:
            raise StaffRuleError(
                "staff.assignment_already_withdrawn", "Esta asignación ya fue retirada."
            )
        self.withdrawal = AssignmentWithdrawal(
            reason=clean_reason(reason), withdrawn_by=withdrawn_by, withdrawn_at=now
        )
        self.status = AssignmentStatus.WITHDRAWN
