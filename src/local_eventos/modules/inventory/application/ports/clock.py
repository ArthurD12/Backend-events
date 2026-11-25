"""Puerto del reloj: instante en UTC y fecha de Lima (AGENTS.md, regla 4)."""

from datetime import date, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def today(self) -> date: ...
