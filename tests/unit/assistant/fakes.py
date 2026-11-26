"""Piezas en memoria para probar el asistente sin base de datos ni red."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from local_eventos.modules.assistant.application.ports.query_log import QueryFilter
from local_eventos.modules.assistant.domain.query_record import QueryRecord


class InMemoryQueryLog:
    def __init__(self) -> None:
        self.records: list[QueryRecord] = []

    async def add(self, record: QueryRecord) -> None:
        self.records.append(record)

    async def count_since(self, user_id: UUID, since: datetime) -> int:
        return sum(1 for r in self.records if r.user_id == user_id and r.created_at >= since)

    async def search(
        self, filters: QueryFilter, *, limit: int, offset: int
    ) -> tuple[list[QueryRecord], int]:
        found = [
            r
            for r in sorted(self.records, key=lambda r: r.created_at, reverse=True)
            if (filters.user_id is None or r.user_id == filters.user_id)
            and (filters.since is None or r.created_at >= filters.since)
            and (filters.until is None or r.created_at <= filters.until)
        ]
        return found[offset : offset + limit], len(found)


class FixedClock:
    def __init__(self, now: datetime | None = None) -> None:
        self.current = now or datetime(2026, 11, 26, 15, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> None:
        self.current += timedelta(**delta)
