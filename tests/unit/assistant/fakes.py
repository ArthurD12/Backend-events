"""Piezas en memoria para probar el asistente sin base de datos ni red."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from local_eventos.modules.assistant.domain.query_record import QueryRecord


class InMemoryQueryLog:
    def __init__(self) -> None:
        self.records: list[QueryRecord] = []

    async def add(self, record: QueryRecord) -> None:
        self.records.append(record)

    async def count_since(self, user_id: UUID, since: datetime) -> int:
        return sum(1 for r in self.records if r.user_id == user_id and r.created_at >= since)


class FixedClock:
    def __init__(self, now: datetime | None = None) -> None:
        self.current = now or datetime(2026, 11, 26, 15, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> None:
        self.current += timedelta(**delta)
