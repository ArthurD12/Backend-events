"""Historial de accesos en PostgreSQL: implementa el puerto `AccessLogRepository` (HU03).

Solo inserta y lee. Además, un trigger de la base rechaza cualquier UPDATE o DELETE.
"""

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.identity.application.ports.access_log_repository import (
    AccessLogEntry,
    AccessLogFilter,
)
from local_eventos.modules.identity.domain.access_attempt import AccessAttempt, AccessResult
from local_eventos.modules.identity.infrastructure.orm_models import AccessLogRow, UserRow


class SqlAlchemyAccessLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, attempt: AccessAttempt) -> None:
        self._session.add(
            AccessLogRow(
                email=attempt.email,
                user_id=attempt.user_id,
                result=attempt.result.value,
                occurred_at=attempt.occurred_at,
            )
        )
        await self._session.flush()

    async def search(
        self, filters: AccessLogFilter, *, limit: int, offset: int
    ) -> tuple[list[AccessLogEntry], int]:
        conditions = _conditions(filters)
        rows = await self._session.execute(
            select(AccessLogRow, UserRow.name)
            .outerjoin(UserRow, UserRow.id == AccessLogRow.user_id)
            .where(*conditions)
            .order_by(AccessLogRow.occurred_at.desc(), AccessLogRow.id.desc())
            .limit(limit)
            .offset(offset)
        )
        total = await self._session.scalar(
            select(func.count()).select_from(AccessLogRow).where(*conditions)
        )
        entries = [
            AccessLogEntry(
                id=row.id,
                email=row.email,
                user_id=row.user_id,
                user_name=user_name,
                result=AccessResult(row.result),
                occurred_at=row.occurred_at,
            )
            for row, user_name in rows
        ]
        return entries, int(total or 0)


def _conditions(filters: AccessLogFilter) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.user_id is not None:
        conditions.append(AccessLogRow.user_id == filters.user_id)
    if filters.result is not None:
        conditions.append(AccessLogRow.result == filters.result.value)
    if filters.since is not None:
        conditions.append(AccessLogRow.occurred_at >= filters.since)
    if filters.until is not None:
        conditions.append(AccessLogRow.occurred_at <= filters.until)
    return conditions
