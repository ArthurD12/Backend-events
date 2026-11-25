"""Actividades y observaciones del evento (HU13): el seguimiento de la preparación del servicio.

Cada registro guarda quién y cuándo (CA-13.2, RN03). Los usuarios son IDs del módulo
`identity`, sin clave foránea entre módulos (AGENTS.md, regla 3).
Python puro: no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from local_eventos.modules.commercial.domain.events.event import (
    EventRuleError,
    EventValidationError,
)

ACTIVITY_MAX_LENGTH = 200  # CA-13.1
NOTE_MAX_LENGTH = 1000  # CA-13.4


class ActivityStatus(StrEnum):
    PENDING = "PENDING"
    DONE = "DONE"


class ActivityAction(StrEnum):
    """Cambio de estado guardado en el historial de la actividad (CA-13.3)."""

    COMPLETED = "COMPLETED"
    REOPENED = "REOPENED"


@dataclass(frozen=True)
class ActivityChange:
    """Una fila del historial: solo se inserta, nunca se cambia ni se borra."""

    activity_id: UUID
    action: ActivityAction
    changed_by: UUID
    changed_at: datetime


@dataclass
class EventActivity:
    """Actividad o indicación del evento (CA-13.1). R-ACT-3 (provisional): no se elimina."""

    id: UUID
    event_id: UUID
    description: str
    status: ActivityStatus
    responsible_id: UUID
    created_by: UUID
    created_at: datetime
    completed_by: UUID | None = None
    completed_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        event_id: UUID,
        description: str,
        responsible_id: UUID,
        created_by: UUID,
        now: datetime,
    ) -> EventActivity:
        """Nace pendiente (CA-13.1). Que el responsable sea válido lo revisa aplicación."""
        return cls(
            id=uuid4(),
            event_id=event_id,
            description=_clean_activity(description),
            status=ActivityStatus.PENDING,
            responsible_id=responsible_id,
            created_by=created_by,
            created_at=now,
        )

    def complete(self, *, by: UUID, now: datetime) -> ActivityChange:
        if self.status is ActivityStatus.DONE:
            raise EventRuleError("activity.already_done", "La actividad ya está completada.")
        self.status = ActivityStatus.DONE
        self.completed_by, self.completed_at = by, now
        return ActivityChange(self.id, ActivityAction.COMPLETED, by, now)

    def reopen(self, *, by: UUID, now: datetime) -> ActivityChange:
        if self.status is ActivityStatus.PENDING:
            raise EventRuleError("activity.already_pending", "La actividad ya está pendiente.")
        self.status = ActivityStatus.PENDING
        self.completed_by, self.completed_at = None, None
        return ActivityChange(self.id, ActivityAction.REOPENED, by, now)

    def change_responsible(self, responsible_id: UUID) -> None:
        """R-ACT-4. Que el responsable sea válido lo revisa aplicación."""
        self.responsible_id = responsible_id


@dataclass
class EventNote:
    """Observación de la bitácora del evento (CA-13.4). No se elimina (R-ACT-1)."""

    id: UUID
    event_id: UUID
    text: str
    created_by: UUID
    created_at: datetime
    edited_by: UUID | None = None
    edited_at: datetime | None = None

    @classmethod
    def create(cls, *, event_id: UUID, text: str, created_by: UUID, now: datetime) -> EventNote:
        return cls(
            id=uuid4(),
            event_id=event_id,
            text=_clean_note(text),
            created_by=created_by,
            created_at=now,
        )

    def can_be_edited_by(self, user_id: UUID, *, is_admin: bool) -> bool:
        """R-ACT-6 (provisional): la edita su autor o un administrador."""
        return is_admin or user_id == self.created_by

    def edit(self, text: str, *, by: UUID, now: datetime) -> None:
        """R-ACT-1: queda quién la editó por última vez y cuándo."""
        self.text = _clean_note(text)
        self.edited_by, self.edited_at = by, now


def _clean_activity(description: str) -> str:
    cleaned = " ".join(description.split())
    if not cleaned or len(cleaned) > ACTIVITY_MAX_LENGTH:
        raise EventValidationError(
            "activity.validation",
            f"La actividad es obligatoria y tiene hasta {ACTIVITY_MAX_LENGTH} caracteres.",
        )
    return cleaned


def _clean_note(text: str) -> str:
    cleaned = text.strip()  # conserva los saltos de línea internos
    if not cleaned or len(cleaned) > NOTE_MAX_LENGTH:
        raise EventValidationError(
            "note.validation",
            f"La observación es obligatoria y tiene hasta {NOTE_MAX_LENGTH} caracteres.",
        )
    return cleaned
