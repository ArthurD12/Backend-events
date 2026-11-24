"""Importe referencial del trabajador en céntimos (HU15, R-STF-7/R-STF-8).

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass

from local_eventos.modules.staff.domain.errors import StaffValidationError

CURRENCY = "PEN"


@dataclass(frozen=True)
class Money:
    """Importe inmutable: entero de céntimos con moneda fija `PEN`. `0` es válido."""

    cents: int
    currency: str = CURRENCY

    def __post_init__(self) -> None:
        if isinstance(self.cents, bool) or not isinstance(self.cents, int):
            raise StaffValidationError(
                "staff.rate_invalid", "La tarifa debe expresarse en céntimos enteros."
            )
        if self.cents < 0:
            raise StaffValidationError("staff.rate_invalid", "La tarifa no puede ser negativa.")
        if self.currency != CURRENCY:
            raise StaffValidationError("staff.rate_invalid", f"La moneda debe ser {CURRENCY}.")
