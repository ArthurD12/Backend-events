"""Registro de consultas del asistente en PostgreSQL: solo inserta y lee (RN33)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.assistant.application.ports.query_log import QueryFilter
from local_eventos.modules.assistant.domain.query_record import QueryRecord, QueryStatus, ToolUse
from local_eventos.modules.assistant.infrastructure.orm_models import QueryRow


class SqlAlchemyQueryLog:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: QueryRecord) -> None:
        self._session.add(
            QueryRow(
                id=record.id,
                user_id=record.user_id,
                created_at=record.created_at,
                question=record.question,
                tools=[{"name": t.name, "input": t.input, "error": t.error} for t in record.tools],
                answer=record.answer,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                duration_ms=record.duration_ms,
                status=record.status.value,
            )
        )
        await self._session.flush()

    async def get(self, query_id: UUID) -> QueryRecord | None:
        row = await self._session.get(QueryRow, query_id)
        return None if row is None else _record(row)

    async def count_since(self, user_id: UUID, since: datetime) -> int:
        total = await self._session.scalar(
            select(func.count())
            .select_from(QueryRow)
            .where(QueryRow.user_id == user_id, QueryRow.created_at >= since)
        )
        return int(total or 0)

    async def search(
        self, filters: QueryFilter, *, limit: int, offset: int
    ) -> tuple[list[QueryRecord], int]:
        conditions: list[ColumnElement[bool]] = []
        if filters.user_id is not None:
            conditions.append(QueryRow.user_id == filters.user_id)
        if filters.since is not None:
            conditions.append(QueryRow.created_at >= filters.since)
        if filters.until is not None:
            conditions.append(QueryRow.created_at <= filters.until)
        rows = await self._session.scalars(
            select(QueryRow)
            .where(*conditions)
            .order_by(QueryRow.created_at.desc(), QueryRow.id.desc())
            .limit(limit)
            .offset(offset)
        )
        total = await self._session.scalar(
            select(func.count()).select_from(QueryRow).where(*conditions)
        )
        return [_record(row) for row in rows], int(total or 0)


def _record(row: QueryRow) -> QueryRecord:
    return QueryRecord(
        id=row.id,
        user_id=row.user_id,
        created_at=row.created_at,
        question=row.question,
        tools=tuple(
            ToolUse(t["name"], t.get("input", {}), bool(t.get("error", False))) for t in row.tools
        ),
        answer=row.answer,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        duration_ms=row.duration_ms,
        status=QueryStatus(row.status),
    )
