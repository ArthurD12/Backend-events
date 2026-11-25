"""Puerto del reloj: la auditoría guarda el instante en UTC (AGENTS.md, regla 4)."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...
