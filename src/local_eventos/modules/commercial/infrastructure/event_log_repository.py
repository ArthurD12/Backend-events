"""Actividades y observaciones del evento en PostgreSQL (HU13): implementa
`EventLogRepository`. El historial de actividades es de solo inserción."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial.domain.events.activity import (
    ActivityAction,
    ActivityChange,
    ActivityStatus,
    EventActivity,
    EventNote,
)
from local_eventos.modules.commercial.infrastructure.orm_models import (
    EventActivityChangeRow,
    EventActivityRow,
    EventNoteRow,
)


class SqlAlchemyEventLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_activity(self, activity_id: UUID) -> EventActivity | None:
        row = await self._session.get(EventActivityRow, activity_id)
        return _activity(row) if row is not None else None

    async def list_activities(self, event_id: UUID) -> list[EventActivity]:
        rows = await self._session.scalars(
            select(EventActivityRow)
            .where(EventActivityRow.event_id == event_id)
            .order_by(EventActivityRow.created_at, EventActivityRow.id)
        )
        return [_activity(row) for row in rows]

    async def add_activity(self, activity: EventActivity) -> None:
        self._session.add(
            EventActivityRow(
                id=activity.id,
                event_id=activity.event_id,
                description=activity.description,
                status=activity.status.value,
                responsible_id=activity.responsible_id,
                created_by=activity.created_by,
                created_at=activity.created_at,
                completed_by=activity.completed_by,
                completed_at=activity.completed_at,
            )
        )
        await self._session.flush()

    async def update_activity(
        self, activity: EventActivity, change: ActivityChange | None = None
    ) -> None:
        """Gana el último que guarda; cada cambio de estado queda en el historial."""
        row = await self._session.get(EventActivityRow, activity.id)
        if row is None:
            raise LookupError(f"La actividad {activity.id} no existe en la base de datos.")
        row.status = activity.status.value
        row.responsible_id = activity.responsible_id
        row.completed_by = activity.completed_by
        row.completed_at = activity.completed_at
        if change is not None:
            self._session.add(
                EventActivityChangeRow(
                    activity_id=change.activity_id,
                    action=change.action.value,
                    changed_by=change.changed_by,
                    changed_at=change.changed_at,
                )
            )
        await self._session.flush()

    async def list_changes(self, activity_id: UUID) -> list[ActivityChange]:
        rows = await self._session.scalars(
            select(EventActivityChangeRow)
            .where(EventActivityChangeRow.activity_id == activity_id)
            .order_by(EventActivityChangeRow.id)
        )
        return [
            ActivityChange(
                activity_id=row.activity_id,
                action=ActivityAction(row.action),
                changed_by=row.changed_by,
                changed_at=row.changed_at,
            )
            for row in rows
        ]

    async def get_note(self, note_id: UUID) -> EventNote | None:
        row = await self._session.get(EventNoteRow, note_id)
        return _note(row) if row is not None else None

    async def list_notes(self, event_id: UUID) -> list[EventNote]:
        rows = await self._session.scalars(
            select(EventNoteRow)
            .where(EventNoteRow.event_id == event_id)
            .order_by(EventNoteRow.created_at.desc(), EventNoteRow.id)
        )
        return [_note(row) for row in rows]

    async def add_note(self, note: EventNote) -> None:
        self._session.add(
            EventNoteRow(
                id=note.id,
                event_id=note.event_id,
                text=note.text,
                created_by=note.created_by,
                created_at=note.created_at,
                edited_by=note.edited_by,
                edited_at=note.edited_at,
            )
        )
        await self._session.flush()

    async def update_note(self, note: EventNote) -> None:
        row = await self._session.get(EventNoteRow, note.id)
        if row is None:
            raise LookupError(f"La observación {note.id} no existe en la base de datos.")
        row.text = note.text
        row.edited_by = note.edited_by
        row.edited_at = note.edited_at
        await self._session.flush()


def _activity(row: EventActivityRow) -> EventActivity:
    return EventActivity(
        id=row.id,
        event_id=row.event_id,
        description=row.description,
        status=ActivityStatus(row.status),
        responsible_id=row.responsible_id,
        created_by=row.created_by,
        created_at=row.created_at,
        completed_by=row.completed_by,
        completed_at=row.completed_at,
    )


def _note(row: EventNoteRow) -> EventNote:
    return EventNote(
        id=row.id,
        event_id=row.event_id,
        text=row.text,
        created_by=row.created_by,
        created_at=row.created_at,
        edited_by=row.edited_by,
        edited_at=row.edited_at,
    )
