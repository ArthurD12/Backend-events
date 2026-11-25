"""Evento de Darze (HU10): el servicio programado que nace de un contrato firmado con adelanto.

Copia lo contratado (cliente, fecha, horario, lugar, invitados y servicios) para que la
planificación (HU11) pueda cambiar sin tocar la cotización ni el contrato.
Python puro: no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from uuid import UUID, uuid4

from local_eventos.modules.commercial.domain.contracts.contract import Contract
from local_eventos.modules.commercial.domain.quotes.quote import (
    EventType,
    LineKind,
    LineUnit,
    Quote,
)


class EventStatus(StrEnum):
    """DOMAIN.md §3. HU10 solo crea eventos programados; los demás estados llegan con HU11."""

    SCHEDULED = "SCHEDULED"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


_REASON_MAX_LENGTH = 500
_CANCELLABLE = (EventStatus.SCHEDULED, EventStatus.CONFIRMED)  # R-EVT-5
_ACTIVITIES_OPEN = (EventStatus.SCHEDULED, EventStatus.CONFIRMED, EventStatus.IN_PROGRESS)


class EventRuleError(Exception):
    """Operación no permitida (responde 409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EventValidationError(Exception):
    """Dato inválido (responde 422)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EventCancellation:
    reason: str
    cancelled_by: UUID
    cancelled_at: datetime


@dataclass(frozen=True)
class EventService:
    """Servicio contratado, copiado de la cotización (sin precios: los montos son del contrato)."""

    kind: LineKind
    service_id: UUID | None
    description: str
    unit: LineUnit
    quantity: int


@dataclass
class Event:
    id: UUID
    code: str
    contract_id: UUID
    quote_id: UUID
    client_id: UUID
    event_type: EventType
    event_date: date
    start_time: time
    end_time: time
    venue: str
    guests: int
    coordinator_id: UUID
    status: EventStatus
    services: tuple[EventService, ...]
    created_by: UUID
    created_at: datetime
    cancellation: EventCancellation | None = None

    @classmethod
    def from_contract(
        cls,
        *,
        code: str,
        contract: Contract,
        quote: Quote,
        coordinator_id: UUID,
        created_by: UUID,
        now: datetime,
    ) -> Event:
        """CA-10.1 y CA-10.2. Que el contrato no tenga otro evento lo revisa aplicación."""
        if not contract.can_become_event:
            raise EventRuleError(
                "event.contract_not_ready",
                "Solo un contrato firmado y con adelanto pagado se convierte en evento.",
            )
        if quote.id != contract.quote_id:
            raise ValueError("La cotización no corresponde al contrato.")
        details = quote.details
        return cls(
            id=uuid4(),
            code=code,
            contract_id=contract.id,
            quote_id=quote.id,
            client_id=contract.client_id,
            event_type=details.event_type,
            event_date=details.event_date,
            start_time=details.start_time,
            end_time=details.end_time,
            venue=details.venue,
            guests=details.guests,
            coordinator_id=coordinator_id,
            status=EventStatus.SCHEDULED,
            services=tuple(
                EventService(
                    kind=line.kind,
                    service_id=line.service_id,
                    description=line.description,
                    unit=line.unit,
                    quantity=line.quantity,
                )
                for line in quote.lines
            ),
            created_by=created_by,
            created_at=now,
        )

    @property
    def ends_next_day(self) -> bool:
        return self.end_time < self.start_time

    @property
    def can_manage_activities(self) -> bool:
        """R-ACT-2: actividades en programado, confirmado y en ejecución."""
        return self.status in _ACTIVITIES_OPEN

    @property
    def can_take_notes(self) -> bool:
        """R-ACT-2: observaciones en todo estado menos cancelado (también finalizado)."""
        return self.status is not EventStatus.CANCELLED

    def check_activities_open(self) -> None:
        if not self.can_manage_activities:
            raise EventRuleError(
                "event.activities_closed",
                "Las actividades solo se registran o marcan en un evento programado, confirmado"
                " o en ejecución.",
            )

    def check_notes_open(self) -> None:
        if not self.can_take_notes:
            raise EventRuleError(
                "event.notes_closed", "En un evento cancelado no se registran observaciones."
            )

    def check_cancellation(self, reason: str) -> str:
        """CA-11.C1 y CA-11.C2. Se valida antes de registrar pagos. Devuelve el motivo limpio."""
        if self.status not in _CANCELLABLE:
            raise EventRuleError(
                "event.not_cancellable",
                "Solo se cancela un evento programado o confirmado.",
            )
        cleaned = " ".join(reason.split())
        if not cleaned:
            raise EventValidationError(
                "event.reason_required", "Para cancelar el evento, indica el motivo."
            )
        if len(cleaned) > _REASON_MAX_LENGTH:
            raise EventValidationError(
                "event.reason_too_long",
                f"El motivo no puede superar {_REASON_MAX_LENGTH} caracteres.",
            )
        return cleaned

    def cancel(self, *, reason: str, cancelled_by: UUID, now: datetime) -> None:
        """CA-11.C5: queda quién canceló y cuándo. El contrato lo anula aplicación (R-EVT-4)."""
        cleaned = self.check_cancellation(reason)
        self.cancellation = EventCancellation(
            reason=cleaned, cancelled_by=cancelled_by, cancelled_at=now
        )
        self.status = EventStatus.CANCELLED


def format_event_code(year: int, number: int) -> str:
    """EVT-AAAA-NNNN; el correlativo se reinicia cada año (DOMAIN.md §4, regla 8)."""
    return f"EVT-{year}-{number:04d}"
