"""Casos de uso de ingresos y egresos (HU21): registrar, anular y listar."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from local_eventos.modules.ledger.application.errors import (
    MovementAlreadyVoidedError,
    MovementNotFoundError,
)
from local_eventos.modules.ledger.application.ports.clock import Clock
from local_eventos.modules.ledger.application.ports.movement_repository import (
    MovementEntry,
    MovementFilters,
    MovementRepository,
)
from local_eventos.modules.ledger.domain.movement import (
    CashMovement,
    MovementCategory,
    MovementType,
    MovementVoid,
)
from local_eventos.modules.ledger.domain.payment import PaymentMethod

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class MovementRequest:
    type: MovementType
    category: MovementCategory
    concept: str
    amount_cents: int
    method: PaymentMethod
    reference: str | None
    occurred_on: date
    event_id: UUID | None
    recorded_by: UUID


@dataclass(frozen=True)
class MovementPage:
    items: list[MovementEntry]
    total: int
    page: int
    page_size: int


class RecordMovement:
    def __init__(self, movements: MovementRepository, clock: Clock) -> None:
        self._movements = movements
        self._clock = clock

    async def __call__(self, request: MovementRequest) -> MovementEntry:
        movement = CashMovement.record(
            type=request.type,
            category=request.category,
            concept=request.concept,
            amount_cents=request.amount_cents,
            method=request.method,
            reference=request.reference,
            occurred_on=request.occurred_on,
            event_id=request.event_id,
            recorded_by=request.recorded_by,
            now=self._clock.now(),
            today=self._clock.today(),
        )
        await self._movements.add(movement)
        return MovementEntry(movement=movement)


class VoidMovement:
    """Anula un movimiento con motivo (CA-21.3, RN17): se inserta la anulación aparte."""

    def __init__(self, movements: MovementRepository, clock: Clock) -> None:
        self._movements = movements
        self._clock = clock

    async def __call__(self, movement_id: UUID, *, reason: str, voided_by: UUID) -> MovementEntry:
        entry = await self._movements.get(movement_id)
        if entry is None:
            raise MovementNotFoundError()
        if entry.void is not None:
            raise MovementAlreadyVoidedError()
        void = MovementVoid.of(
            entry.movement, reason=reason, voided_by=voided_by, now=self._clock.now()
        )
        await self._movements.add_void(void)
        return MovementEntry(movement=entry.movement, void=void)


class ListMovements:
    def __init__(self, movements: MovementRepository) -> None:
        self._movements = movements

    async def __call__(
        self, filters: MovementFilters, *, page: int = 1, page_size: int = 20
    ) -> MovementPage:
        page = max(page, 1)
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        items, total = await self._movements.search(
            filters, limit=page_size, offset=(page - 1) * page_size
        )
        return MovementPage(items=items, total=total, page=page, page_size=page_size)
