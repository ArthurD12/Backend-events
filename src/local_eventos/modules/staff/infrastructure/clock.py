"""Reloj del sistema: instante en UTC (AGENTS.md, regla 4)."""

from datetime import UTC, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
