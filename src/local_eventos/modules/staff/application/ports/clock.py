"""Puerto del reloj del personal (HU15).

Los casos de uso reciben el instante de auditoría desde este puerto para que los
tests sean deterministas. Python puro: solo stdlib y `typing` (AGENTS.md, regla 2).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Fuente del instante actual."""

    def now(self) -> datetime:
        """Instante actual en UTC y timezone-aware (AGENTS.md, regla 4)."""
        ...
