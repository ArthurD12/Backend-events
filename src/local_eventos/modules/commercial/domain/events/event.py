"""Evento de Darze (HU10): el servicio programado que nace de un contrato firmado con adelanto.

Copia lo contratado (cliente, fecha, horario, lugar, invitados y servicios) para que la
planificación (HU11) pueda cambiar sin tocar la cotización ni el contrato (R-EVT-7). Cada
cambio de planificación o de estado deja un `EventChange` en el historial (CA-11.5, RN03).
Python puro: no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
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
    """DOMAIN.md §3: programado → confirmado → en ejecución → finalizado · cancelado."""

    SCHEDULED = "SCHEDULED"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class EventAction(StrEnum):
    """Qué cambió en el evento, para el historial (CA-11.5)."""

    PLANNING_UPDATED = "PLANNING_UPDATED"
    CONFIRMED = "CONFIRMED"
    STARTED = "STARTED"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class PlanningWarning(StrEnum):
    """R-EVT-9: cambió la fecha o el horario; el personal asignado puede tener otro horario."""

    STAFF_MAY_NEED_REVIEW = "staff_may_need_review"


_REASON_MAX_LENGTH = 500
_VENUE_MAX_LENGTH = 300  # como en la cotización
_MAX_GUESTS = 10_000  # como en la cotización
_CANCELLABLE = (EventStatus.SCHEDULED, EventStatus.CONFIRMED)  # R-EVT-5
_EDITABLE = (EventStatus.SCHEDULED, EventStatus.CONFIRMED)  # R-EVT-6
_SCHEDULE_FIELDS = frozenset({"event_date", "start_time", "end_time"})
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


FieldValue = str | int
"""Valor de un campo en el historial: fechas y horas en ISO, IDs como texto, invitados entero."""


@dataclass(frozen=True)
class FieldChange:
    field: str
    before: FieldValue
    after: FieldValue


@dataclass(frozen=True)
class EventChange:
    """Una fila del historial del evento: solo se inserta, nunca se cambia ni se borra."""

    event_id: UUID
    action: EventAction
    fields: tuple[FieldChange, ...]
    changed_by: UUID
    changed_at: datetime

    @property
    def warnings(self) -> tuple[PlanningWarning, ...]:
        """R-EVT-9: avisa si cambió la fecha o el horario."""
        if any(f.field in _SCHEDULE_FIELDS for f in self.fields):
            return (PlanningWarning.STAFF_MAY_NEED_REVIEW,)
        return ()


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
        """R-COT-1: si la hora de fin es menor que la de inicio, termina al día siguiente."""
        return self.end_time < self.start_time

    @property
    def can_edit_planning(self) -> bool:
        """R-EVT-6: la planificación se edita en programado y confirmado."""
        return self.status in _EDITABLE

    def is_event_day(self, today: date) -> bool:
        """R-EVT-8 con R-COT-1: el día del evento y, si cruza la medianoche, también el
        siguiente. `today` es la fecha de Lima."""
        if today == self.event_date:
            return True
        return self.ends_next_day and today == self.event_date + timedelta(days=1)

    def update_planning(
        self,
        *,
        event_date: date,
        start_time: time,
        end_time: time,
        venue: str,
        guests: int,
        coordinator_id: UUID,
        by: UUID,
        now: datetime,
        today: date,
    ) -> EventChange | None:
        """CA-11.2. Devuelve los campos cambiados (antes/después) o `None` si no cambió nada.

        No toca el contrato ni la cotización (R-EVT-7). Que el responsable sea válido lo revisa
        aplicación (RN09).
        """
        if not self.can_edit_planning:
            raise EventRuleError(
                "event.not_editable",
                "La planificación solo se edita en un evento programado o confirmado.",
            )
        cleaned_venue = _check_planning(event_date, start_time, end_time, venue, guests, today)
        new: dict[str, FieldValue] = {
            "event_date": event_date.isoformat(),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "venue": cleaned_venue,
            "guests": guests,
            "coordinator_id": str(coordinator_id),
        }
        old = self._planning_values()
        fields = tuple(FieldChange(k, old[k], new[k]) for k in new if old[k] != new[k])
        if not fields:
            return None
        self.event_date, self.start_time, self.end_time = event_date, start_time, end_time
        self.venue, self.guests, self.coordinator_id = cleaned_venue, guests, coordinator_id
        return EventChange(self.id, EventAction.PLANNING_UPDATED, fields, by, now)

    def confirm(self, *, by: UUID, now: datetime) -> EventChange:
        """CA-11.4: programado → confirmado."""
        return self._move(EventStatus.SCHEDULED, EventStatus.CONFIRMED, EventAction.CONFIRMED,
                          by=by, now=now)  # fmt: skip

    def start(self, *, by: UUID, now: datetime, today: date) -> EventChange:
        """CA-11.4 y R-EVT-8: confirmado → en ejecución, solo el día del evento."""
        self._check_from(EventStatus.CONFIRMED)
        if not self.is_event_day(today):
            raise EventRuleError(
                "event.not_event_day", "El evento solo se pone en ejecución el día del evento."
            )
        return self._move(EventStatus.CONFIRMED, EventStatus.IN_PROGRESS, EventAction.STARTED,
                          by=by, now=now)  # fmt: skip

    def finish(self, *, by: UUID, now: datetime) -> EventChange:
        """CA-11.4 y R-EVT-8: en ejecución → finalizado. No exige saldo en cero."""
        return self._move(EventStatus.IN_PROGRESS, EventStatus.FINISHED, EventAction.FINISHED,
                          by=by, now=now)  # fmt: skip

    def _check_from(self, expected: EventStatus) -> None:
        if self.status is not expected:
            raise EventRuleError(
                "event.invalid_transition",
                "El evento avanza un estado a la vez y no vuelve atrás.",
            )

    def _move(
        self,
        expected: EventStatus,
        target: EventStatus,
        action: EventAction,
        *,
        by: UUID,
        now: datetime,
    ) -> EventChange:
        self._check_from(expected)
        self.status = target
        return EventChange(
            self.id, action, (FieldChange("status", expected.value, target.value),), by, now
        )

    def _planning_values(self) -> dict[str, FieldValue]:
        return {
            "event_date": self.event_date.isoformat(),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "venue": self.venue,
            "guests": self.guests,
            "coordinator_id": str(self.coordinator_id),
        }

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

    def cancel(self, *, reason: str, cancelled_by: UUID, now: datetime) -> EventChange:
        """CA-11.C5: queda quién canceló y cuándo. El contrato lo anula aplicación (R-EVT-4)."""
        cleaned = self.check_cancellation(reason)
        before = self.status
        self.cancellation = EventCancellation(
            reason=cleaned, cancelled_by=cancelled_by, cancelled_at=now
        )
        self.status = EventStatus.CANCELLED
        return EventChange(
            self.id,
            EventAction.CANCELLED,
            (FieldChange("status", before.value, EventStatus.CANCELLED.value),),
            cancelled_by,
            now,
        )


def _check_planning(
    event_date: date, start_time: time, end_time: time, venue: str, guests: int, today: date
) -> str:
    """CA-11.2, con las reglas de la cotización (R-COT-1, R-COT-4). Devuelve el lugar limpio."""
    if event_date < today:
        raise EventValidationError(
            "event.date_past", "La fecha del evento debe ser hoy o una fecha futura."
        )
    if start_time == end_time:
        raise EventValidationError(
            "event.time_invalid", "La hora de inicio y la de fin no pueden ser iguales."
        )
    if isinstance(guests, bool) or not 1 <= guests <= _MAX_GUESTS:
        raise EventValidationError(
            "event.guests_invalid", f"La cantidad de invitados debe estar entre 1 y {_MAX_GUESTS}."
        )
    cleaned = " ".join(venue.split())
    if not cleaned:
        raise EventValidationError("event.venue_required", "El lugar del evento es obligatorio.")
    if len(cleaned) > _VENUE_MAX_LENGTH:
        raise EventValidationError(
            "event.venue_too_long", f"El lugar no puede superar {_VENUE_MAX_LENGTH} caracteres."
        )
    return cleaned


def format_event_code(year: int, number: int) -> str:
    """EVT-AAAA-NNNN; el correlativo se reinicia cada año (DOMAIN.md §4, regla 8)."""
    return f"EVT-{year}-{number:04d}"
