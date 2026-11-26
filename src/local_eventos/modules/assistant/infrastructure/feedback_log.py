"""Valoraciones del asistente en PostgreSQL: solo inserta y lee."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.assistant.domain.feedback import Feedback, FeedbackValue
from local_eventos.modules.assistant.infrastructure.orm_models import FeedbackRow


class SqlAlchemyFeedbackLog:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, feedback: Feedback) -> None:
        self._session.add(
            FeedbackRow(
                query_id=feedback.query_id,
                user_id=feedback.user_id,
                value=feedback.value.value,
                comment=feedback.comment,
                created_at=feedback.created_at,
            )
        )
        await self._session.flush()

    async def latest(self, query_ids: list[UUID]) -> dict[UUID, Feedback]:
        if not query_ids:
            return {}
        newest = (
            select(func.max(FeedbackRow.id))
            .where(FeedbackRow.query_id.in_(query_ids))
            .group_by(FeedbackRow.query_id)
        )
        rows = await self._session.scalars(select(FeedbackRow).where(FeedbackRow.id.in_(newest)))
        return {
            row.query_id: Feedback(
                row.query_id, row.user_id, FeedbackValue(row.value), row.comment, row.created_at
            )
            for row in rows
        }
