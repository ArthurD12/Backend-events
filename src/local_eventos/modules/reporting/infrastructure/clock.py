"""Reloj del sistema para los reportes: el instante de generación en UTC."""

from datetime import UTC, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
