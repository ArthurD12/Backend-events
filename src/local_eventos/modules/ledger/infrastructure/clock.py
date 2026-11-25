"""Reloj del sistema para el dinero: instante en UTC y fecha de Lima (siempre UTC−5)."""

from datetime import UTC, date, datetime, timedelta, timezone

LIMA = timezone(timedelta(hours=-5), "America/Lima")


class LimaClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def today(self) -> date:
        return datetime.now(LIMA).date()
