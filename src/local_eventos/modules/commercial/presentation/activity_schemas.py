"""Forma de las actividades y observaciones del evento en la API (HU13).

Los nombres salen de `identity` por su `public_api`: vienen vacíos si el usuario ya no es un
administrador o encargado de eventos activo (y no es quien consulta).
"""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.commercial.domain.events.activity import (
    ActivityStatus,
    EventActivity,
    EventNote,
)

_NAME = "Vacío si no se conoce el nombre del usuario"


class ActivityIn(BaseModel):
    description: str = Field(description="Hasta 200 caracteres")
    responsible_id: UUID | None = Field(
        default=None,
        description="Administrador o encargado de eventos activo. Si se omite: quien crea",
    )


class ActivityResponsibleIn(BaseModel):
    responsible_id: UUID


class NoteIn(BaseModel):
    text: str = Field(description="Hasta 1000 caracteres")


class ActivityOut(BaseModel):
    id: UUID
    event_id: UUID
    description: str
    status: ActivityStatus
    responsible_id: UUID
    responsible_name: str | None = Field(description=_NAME)
    created_by: UUID
    created_by_name: str | None = Field(description=_NAME)
    created_at: datetime
    completed_by: UUID | None
    completed_by_name: str | None = Field(description=_NAME)
    completed_at: datetime | None

    @classmethod
    def from_activity(cls, activity: EventActivity, names: dict[UUID, str]) -> Self:
        return cls(
            id=activity.id,
            event_id=activity.event_id,
            description=activity.description,
            status=activity.status,
            responsible_id=activity.responsible_id,
            responsible_name=names.get(activity.responsible_id),
            created_by=activity.created_by,
            created_by_name=names.get(activity.created_by),
            created_at=activity.created_at,
            completed_by=activity.completed_by,
            completed_by_name=names.get(activity.completed_by) if activity.completed_by else None,
            completed_at=activity.completed_at,
        )


class NoteOut(BaseModel):
    id: UUID
    event_id: UUID
    text: str
    created_by: UUID
    created_by_name: str | None = Field(description=_NAME)
    created_at: datetime
    edited_by: UUID | None = Field(description="Quién la editó por última vez")
    edited_by_name: str | None = Field(description=_NAME)
    edited_at: datetime | None

    @classmethod
    def from_note(cls, note: EventNote, names: dict[UUID, str]) -> Self:
        return cls(
            id=note.id,
            event_id=note.event_id,
            text=note.text,
            created_by=note.created_by,
            created_by_name=names.get(note.created_by),
            created_at=note.created_at,
            edited_by=note.edited_by,
            edited_by_name=names.get(note.edited_by) if note.edited_by else None,
            edited_at=note.edited_at,
        )
