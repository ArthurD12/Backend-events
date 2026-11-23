"""Cotización de Darze (HU07–HU08): la propuesta económica para un evento.

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
Los precios de cada línea quedan congelados: cambiar el catálogo no altera la cotización
(AGENTS.md, regla 6). Dinero en céntimos, moneda PEN, sin IGV aparte (DOMAIN.md §4, regla 9).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

CURRENCY = "PEN"
DEFAULT_VALIDITY = timedelta(days=15)  # DOMAIN.md §4, regla 7 (provisional)
_VENUE_MAX_LENGTH = 300
_DESCRIPTION_MAX_LENGTH = 200
_NOTES_MAX_LENGTH = 1000
_MAX_GUESTS = 10_000


class EventType(StrEnum):
    """Lista fija de tipos de evento (DOMAIN.md §4, regla 13)."""

    WEDDING = "WEDDING"
    BIRTHDAY = "BIRTHDAY"
    QUINCEANERA = "QUINCEANERA"
    CORPORATE = "CORPORATE"
    GRADUATION = "GRADUATION"
    OTHER = "OTHER"


class QuoteStatus(StrEnum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"  # no se guarda: se calcula con la vigencia (CA-08.3)


class LineKind(StrEnum):
    SERVICE = "SERVICE"  # servicio del catálogo
    EXTRA = "EXTRA"  # concepto adicional libre: movilidad, recargo… (regla 12)


class LineUnit(StrEnum):
    PER_PERSON = "PER_PERSON"
    PER_UNIT = "PER_UNIT"


# R-COT-3: transiciones permitidas. Aceptada y rechazada son finales.
_TRANSITIONS: dict[QuoteStatus, frozenset[QuoteStatus]] = {
    QuoteStatus.DRAFT: frozenset({QuoteStatus.SENT, QuoteStatus.ACCEPTED, QuoteStatus.REJECTED}),
    QuoteStatus.SENT: frozenset({QuoteStatus.ACCEPTED, QuoteStatus.REJECTED, QuoteStatus.DRAFT}),
}


class QuoteValidationError(ValueError):
    """Dato inválido (responde 422). `code` es estable para que el frontend lo traduzca."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class QuoteRuleError(Exception):
    """La operación no está permitida en el estado actual (responde 409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EventDetails:
    event_type: EventType
    event_date: date
    start_time: time
    end_time: time
    venue: str
    guests: int

    def checked(self, today: date) -> EventDetails:
        """Valida y limpia los datos. `today` es la fecha de Lima."""
        if self.event_date < today:
            raise QuoteValidationError(
                "quote.event_date_past", "La fecha del evento debe ser hoy o una fecha futura."
            )
        if self.start_time == self.end_time:
            raise QuoteValidationError(
                "quote.time_invalid", "La hora de inicio y la de fin no pueden ser iguales."
            )
        if isinstance(self.guests, bool) or not 1 <= self.guests <= _MAX_GUESTS:
            raise QuoteValidationError(
                "quote.guests_invalid",
                f"La cantidad de invitados debe estar entre 1 y {_MAX_GUESTS}.",
            )
        venue = " ".join(self.venue.split())
        if not venue:
            raise QuoteValidationError(
                "quote.venue_required", "El lugar del evento es obligatorio."
            )
        if len(venue) > _VENUE_MAX_LENGTH:
            raise QuoteValidationError(
                "quote.venue_too_long",
                f"El lugar no puede superar {_VENUE_MAX_LENGTH} caracteres.",
            )
        return replace(self, venue=venue)

    @property
    def ends_next_day(self) -> bool:
        """R-COT-1: si la hora de fin es menor que la de inicio, termina al día siguiente."""
        return self.end_time < self.start_time


@dataclass(frozen=True)
class QuoteLine:
    kind: LineKind
    description: str
    unit: LineUnit
    quantity: int
    unit_price_cents: int  # precio acordado (editable en borrador, regla 10)
    service_id: UUID | None = None
    catalog_price_cents: int | None = None  # precio del catálogo al agregar la línea

    def __post_init__(self) -> None:
        description = " ".join(self.description.split())
        if not description:
            raise QuoteValidationError(
                "quote.description_required", "Cada línea necesita una descripción."
            )
        if len(description) > _DESCRIPTION_MAX_LENGTH:
            raise QuoteValidationError(
                "quote.description_too_long",
                f"La descripción no puede superar {_DESCRIPTION_MAX_LENGTH} caracteres.",
            )
        object.__setattr__(self, "description", description)
        if not _is_int(self.quantity) or self.quantity < 1:
            raise QuoteValidationError(
                "quote.quantity_invalid", "La cantidad debe ser un número entero mayor que cero."
            )
        if not _is_int(self.unit_price_cents) or self.unit_price_cents < 0:
            raise QuoteValidationError(
                "quote.price_invalid", "El precio debe ser un monto en céntimos, cero o mayor."
            )
        if (self.kind is LineKind.SERVICE) != (self.service_id is not None):
            raise QuoteValidationError(
                "quote.line_invalid", "Solo las líneas de servicio llevan un servicio del catálogo."
            )

    @property
    def subtotal_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass
class Quote:
    id: UUID
    code: str
    client_id: UUID
    details: EventDetails
    valid_until: date
    lines: tuple[QuoteLine, ...]
    status: QuoteStatus
    created_by: UUID
    created_at: datetime
    notes: str | None = None

    @classmethod
    def create(
        cls,
        *,
        code: str,
        client_id: UUID,
        details: EventDetails,
        lines: list[QuoteLine],
        created_by: UUID,
        now: datetime,
        today: date,
        valid_until: date | None = None,
        notes: str | None = None,
    ) -> Quote:
        """Crea la cotización en borrador (CA-07.6). Que el cliente esté activo se verifica en
        aplicación."""
        return cls(
            id=uuid4(),
            code=code,
            client_id=client_id,
            details=details.checked(today),
            valid_until=_check_valid_until(valid_until or today + DEFAULT_VALIDITY, today),
            lines=_check_lines(lines),
            status=QuoteStatus.DRAFT,
            created_by=created_by,
            created_at=now,
            notes=_clean_notes(notes),
        )

    @property
    def total_cents(self) -> int:
        return sum(line.subtotal_cents for line in self.lines)

    def effective_status(self, today: date) -> QuoteStatus:
        """Vencida si pasó la vigencia sin ser aceptada ni rechazada (CA-08.3)."""
        if self.status in (QuoteStatus.DRAFT, QuoteStatus.SENT) and self.valid_until < today:
            return QuoteStatus.EXPIRED
        return self.status

    def update(
        self,
        *,
        details: EventDetails,
        lines: list[QuoteLine],
        valid_until: date,
        today: date,
        notes: str | None = None,
    ) -> None:
        """Solo en borrador y no vencida (CA-08.1, CA-08.4). Valida todo antes de asignar."""
        self.ensure_editable(today)
        new_details = details.checked(today)
        new_valid_until = _check_valid_until(valid_until, today)
        new_lines = _check_lines(lines)
        new_notes = _clean_notes(notes)
        self.details = new_details
        self.valid_until = new_valid_until
        self.lines = new_lines
        self.notes = new_notes

    def ensure_editable(self, today: date) -> None:
        if self.effective_status(today) is not QuoteStatus.DRAFT:
            raise QuoteRuleError(
                "quote.not_editable",
                "Solo se modifica en borrador. Si fue enviada, devuélvela a borrador primero.",
            )

    def change_status(self, new_status: QuoteStatus, today: date) -> None:
        current = self.effective_status(today)
        if current is QuoteStatus.EXPIRED:
            raise QuoteRuleError(
                "quote.expired",
                "La cotización venció: no cambia de estado. Crea una nueva (regla 14).",
            )
        if new_status not in _TRANSITIONS.get(current, frozenset()):
            raise QuoteRuleError(
                "quote.invalid_transition",
                f"No se puede pasar de {current.value} a {new_status.value}.",
            )
        self.status = new_status


def format_code(year: int, number: int) -> str:
    """COT-AAAA-NNNN; el correlativo se reinicia cada año (DOMAIN.md §4, regla 8)."""
    return f"COT-{year}-{number:04d}"


def _check_lines(lines: list[QuoteLine]) -> tuple[QuoteLine, ...]:
    if not lines:
        raise QuoteValidationError(
            "quote.lines_required", "Agrega al menos un servicio o concepto a la cotización."
        )
    return tuple(lines)


def _check_valid_until(valid_until: date, today: date) -> date:
    if valid_until < today:
        raise QuoteValidationError(
            "quote.valid_until_invalid", "La vigencia debe terminar hoy o en una fecha futura."
        )
    return valid_until


def _clean_notes(notes: str | None) -> str | None:
    if notes is None:
        return None
    cleaned = notes.strip()
    if len(cleaned) > _NOTES_MAX_LENGTH:
        raise QuoteValidationError(
            "quote.notes_too_long", f"Las notas no pueden superar {_NOTES_MAX_LENGTH} caracteres."
        )
    return cleaned or None


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
