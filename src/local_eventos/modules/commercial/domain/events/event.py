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


class EventRuleError(Exception):
    """Operación no permitida (responde 409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


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


def format_event_code(year: int, number: int) -> str:
    """EVT-AAAA-NNNN; el correlativo se reinicia cada año (DOMAIN.md §4, regla 8)."""
    return f"EVT-{year}-{number:04d}"
