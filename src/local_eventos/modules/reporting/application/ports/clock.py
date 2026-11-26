"""Puerto del reloj: el instante (UTC) en que se genera un reporte."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...
