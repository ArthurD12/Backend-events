"""Puerto del reloj: la vigencia y la fecha del evento se comparan con la fecha de Lima."""

from datetime import date, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Instante actual en UTC (AGENTS.md, regla 4)."""
        ...

    def today(self) -> date:
        """Fecha actual en Lima: la que ve el encargado al cotizar."""
        ...
