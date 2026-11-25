"""Puerto del reloj: instante en UTC y fecha de Lima (para no aceptar fechas futuras)."""

from datetime import date, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Instante actual en UTC (AGENTS.md, regla 4)."""
        ...

    def today(self) -> date:
        """Fecha actual en Lima."""
        ...
