"""Casos de uso de movimientos (HU23, HU26): entrada, salida, devolución, merma y ajuste.

Cada movimiento bloquea el stock del producto (`StockRepository.lock`), valida, guarda el
movimiento y el stock nuevo en la misma transacción. Así dos salidas simultáneas no dejan el
stock negativo (RN20): la segunda espera a la primera y ve el stock ya descontado.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from local_eventos.modules.commercial.public_api import EventLookup, EventStatus
from local_eventos.modules.inventory.application.errors import (
    EventNotAssignableError,
    EventNotFoundError,
    ProductInactiveError,
    ProductNotFoundError,
    ReturnExceedsError,
    WasteExceedsError,
)
from local_eventos.modules.inventory.application.ports.clock import Clock
from local_eventos.modules.inventory.application.ports.product_repository import (
    ProductRepository,
)
from local_eventos.modules.inventory.application.ports.stock_repository import (
    MovementRepository,
    StockRepository,
)
from local_eventos.modules.inventory.domain.event_materials import EventMaterials
from local_eventos.modules.inventory.domain.movement import Movement, MovementKind
from local_eventos.modules.inventory.domain.stock import StockLevel

_ASSIGNABLE = (EventStatus.SCHEDULED, EventStatus.CONFIRMED, EventStatus.IN_PROGRESS)
_NEEDS_ACTIVE = (MovementKind.ENTRY, MovementKind.EXIT)


@dataclass(frozen=True)
class MovementCommand:
    """Datos de un movimiento. Cada tipo usa solo los suyos; el dominio rechaza los demás."""

    kind: MovementKind
    product_id: UUID
    quantity: Decimal
    occurred_on: date | None = None
    event_id: UUID | None = None
    unit_cost_cents: int | None = None
    supplier_id: UUID | None = None
    lot: str | None = None
    expires_on: date | None = None
    reason: str | None = None
    purchase_id: UUID | None = None


@dataclass(frozen=True)
class RecordedMovement:
    movement: Movement
    stock: StockLevel


class RecordMovement:
    def __init__(
        self,
        products: ProductRepository,
        stock: StockRepository,
        movements: MovementRepository,
        events: EventLookup,
        clock: Clock,
    ) -> None:
        self._products = products
        self._stock = stock
        self._movements = movements
        self._events = events
        self._clock = clock

    async def __call__(self, command: MovementCommand, *, recorded_by: UUID) -> RecordedMovement:
        product = await self._products.get(command.product_id)
        if product is None:
            raise ProductNotFoundError()
        if not product.active and command.kind in _NEEDS_ACTIVE:
            raise ProductInactiveError()
        movement = Movement.record(
            kind=command.kind,
            product_id=command.product_id,
            quantity=command.quantity,
            recorded_by=recorded_by,
            now=self._clock.now(),
            today=self._clock.today(),
            occurred_on=command.occurred_on,
            event_id=command.event_id,
            unit_cost_cents=command.unit_cost_cents,
            supplier_id=command.supplier_id,
            lot=command.lot,
            expires_on=command.expires_on,
            reason=command.reason,
            purchase_id=command.purchase_id,
        )
        if movement.event_id is not None:
            event = await self._events(movement.event_id)
            if event is None:
                raise EventNotFoundError()
            if movement.kind is MovementKind.EXIT and event.status not in _ASSIGNABLE:
                raise EventNotAssignableError()
        # Primero el bloqueo: lo que sigue se calcula con el stock ya reservado.
        level = await self._stock.lock(product.id)
        if movement.event_id is not None and movement.kind is not MovementKind.EXIT:
            materials = EventMaterials.from_movements(
                product.id,
                product.kind,
                await self._movements.list_for_event(movement.event_id, product.id),
            )
            if movement.quantity > materials.at_event:
                if movement.kind is MovementKind.RETURN:
                    raise ReturnExceedsError(materials.at_event)
                raise WasteExceedsError(materials.at_event)
        new_level = level.apply(movement)
        await self._movements.add(movement)
        await self._stock.save(new_level)
        return RecordedMovement(movement=movement, stock=new_level)


@dataclass(frozen=True)
class StockEntry:
    """Entrada que otro módulo registra (una línea de compra recibida, HU29)."""

    product_id: UUID
    quantity: Decimal
    unit_cost_cents: int
    supplier_id: UUID | None = None
    lot: str | None = None
    expires_on: date | None = None
    purchase_id: UUID | None = None
    occurred_on: date | None = None


class RecordEntries:
    """Varias entradas en la misma transacción (recepción de una compra, HU29).

    Bloquea los productos siempre en el mismo orden para no trabarse con otra recepción.
    """

    def __init__(self, record: RecordMovement) -> None:
        self._record = record

    async def __call__(
        self, entries: list[StockEntry], *, recorded_by: UUID
    ) -> list[RecordedMovement]:
        ordered = sorted(entries, key=lambda e: str(e.product_id))
        return [
            await self._record(
                MovementCommand(
                    kind=MovementKind.ENTRY,
                    product_id=e.product_id,
                    quantity=e.quantity,
                    unit_cost_cents=e.unit_cost_cents,
                    supplier_id=e.supplier_id,
                    lot=e.lot,
                    expires_on=e.expires_on,
                    purchase_id=e.purchase_id,
                    occurred_on=e.occurred_on,
                ),
                recorded_by=recorded_by,
            )
            for e in ordered
        ]
