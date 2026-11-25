"""Reloj del sistema para el personal (HU15): instante actual en UTC y aware.

Lo usan los casos de uso para escribir `changed_at` de la auditoría de forma
determinista en los tests (AGENTS.md, regla 4).
"""

from datetime import UTC, datetime


class SystemClock:
    """Fuente real del instante actual, en UTC y con zona horaria."""

    def now(self) -> datetime:
        return datetime.now(UTC)
