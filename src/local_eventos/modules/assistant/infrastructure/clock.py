"""Reloj del sistema para el asistente: instante en UTC y fecha de hoy en Lima."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

LIMA = ZoneInfo("America/Lima")


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def today(self) -> date:
        return datetime.now(LIMA).date()
