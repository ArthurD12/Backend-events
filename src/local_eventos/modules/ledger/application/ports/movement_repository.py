"""Puerto: dónde se guardan los ingresos, egresos y sus anulaciones. Solo se agregan y se leen."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from local_eventos.modules.ledger.domain.movement import (
    CashMovement,
    MovementCategory,
    MovementType,
    MovementVoid,
)


class MovementState(StrEnum):
    ACTIVE = "ACTIVE"
    VOIDED = "VOIDED"


@dataclass(frozen=True)
class MovementEntry:
    movement: CashMovement
    void: MovementVoid | None = None


@dataclass(frozen=True)
class MovementFilters:
    """CA-21.4: por fechas, tipo, categoría, evento y estado."""

    date_from: date | None = None
    date_to: date | None = None
    type: MovementType | None = None
    category: MovementCategory | None = None
    event_id: UUID | None = None
    state: MovementState | None = None


@dataclass(frozen=True)
class MonthlyMovementTotal:
    """Suma de movimientos vigentes de una categoría en un mes, por fecha del movimiento."""

    year: int
    month: int
    category: MovementCategory
    amount_cents: int


class MovementRepository(Protocol):
    async def add(self, movement: CashMovement) -> None: ...

    async def get(self, movement_id: UUID) -> MovementEntry | None: ...

    async def add_void(self, void: MovementVoid) -> None:
        """Si el movimiento ya tiene anulación, lanza `MovementAlreadyVoidedError`."""
        ...

    async def search(
        self, filters: MovementFilters, *, limit: int, offset: int
    ) -> tuple[list[MovementEntry], int]:
        """Una página, de la fecha más reciente a la más antigua, y el total que cumple."""
        ...

    async def monthly_totals(self, date_from: date, date_to: date) -> list[MonthlyMovementTotal]:
        """Movimientos vigentes del rango, sumados por mes y categoría."""
        ...

    async def event_totals(self, event_id: UUID) -> dict[MovementCategory, int]:
        """Movimientos vigentes asociados al evento, sumados por categoría."""
        ...
