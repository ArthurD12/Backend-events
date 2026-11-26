"""Reservas de materiales para un evento (HU25, CA-25.4 y CA-25.5, R-REC-3).

Reservar bloquea el stock del producto (`FOR UPDATE`, como las salidas): el disponible para
otros nunca queda negativo aunque dos personas reserven a la vez.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from local_eventos.modules.commercial.public_api import EventLookup, EventStatus
from local_eventos.modules.inventory.application.errors import (
    EventNotAssignableError,
    EventNotFoundError,
    InsufficientAvailableError,
    ProductInactiveError,
    ProductNotFoundError,
    ReservationNotFoundError,
)
from local_eventos.modules.inventory.application.ports.clock import Clock
from local_eventos.modules.inventory.application.ports.product_repository import (
    ProductRepository,
)
from local_eventos.modules.inventory.application.ports.reservation_repository import (
    ReservationRepository,
)
from local_eventos.modules.inventory.application.ports.stock_repository import StockRepository
from local_eventos.modules.inventory.domain.errors import InventoryValidationError
from local_eventos.modules.inventory.domain.product import Product
from local_eventos.modules.inventory.domain.quantity import ZERO
from local_eventos.modules.inventory.domain.reservation import (
    Reservation,
    check_reserved_quantity,
)

_RESERVABLE = (EventStatus.SCHEDULED, EventStatus.CONFIRMED, EventStatus.IN_PROGRESS)


@dataclass(frozen=True)
class ReservationLine:
    product: Product
    reservation: Reservation


class _Lines:
    def __init__(self, products: ProductRepository, reservations: ReservationRepository) -> None:
        self._products = products
        self._reservations = reservations

    async def __call__(self, event_id: UUID) -> list[ReservationLine]:
        active = await self._reservations.active_for_event(event_id)
        found = {p.id: p for p in await self._products.get_many([r.product_id for r in active])}
        lines = [ReservationLine(found[r.product_id], r) for r in active if r.product_id in found]
        return sorted(lines, key=lambda line: line.product.name.lower())


class ReserveMaterials:
    def __init__(
        self,
        products: ProductRepository,
        stock: StockRepository,
        reservations: ReservationRepository,
        events: EventLookup,
        clock: Clock,
    ) -> None:
        self._products = products
        self._stock = stock
        self._reservations = reservations
        self._events = events
        self._clock = clock

    async def __call__(
        self, event_id: UUID, items: list[tuple[UUID, Decimal]], *, by: UUID
    ) -> list[ReservationLine]:
        """Aparta cada cantidad pedida (se suma a lo que el evento ya tenía reservado)."""
        if not items:
            raise InventoryValidationError("Indica al menos un producto para reservar.")
        wanted: dict[UUID, Decimal] = {}
        for product_id, quantity in items:
            amount = check_reserved_quantity(quantity)
            wanted[product_id] = wanted.get(product_id, ZERO) + amount
        event = await self._events(event_id)
        if event is None:
            raise EventNotFoundError()
        if event.status not in _RESERVABLE:
            raise EventNotAssignableError()
        now = self._clock.now()
        for product_id in sorted(wanted, key=str):  # mismo orden de bloqueo siempre
            product = await self._products.get(product_id)
            if product is None:
                raise ProductNotFoundError()
            if not product.active:
                raise ProductInactiveError()
            level = await self._stock.lock(product_id)  # primero el bloqueo
            totals = await self._reservations.active_totals([product_id])
            available = level.quantity - totals.get(product_id, ZERO)
            if wanted[product_id] > available:
                raise InsufficientAvailableError(max(ZERO, available))
            current = await self._reservations.get_active(event_id, product_id)
            if current is None:
                current = Reservation.open(
                    event_id=event_id,
                    product_id=product_id,
                    quantity=wanted[product_id],
                    by=by,
                    now=now,
                )
            else:
                current.add(wanted[product_id])
            await self._reservations.save(current)
        return await _Lines(self._products, self._reservations)(event_id)


class ReleaseReservation:
    """Libera la reserva vigente de un producto del evento."""

    def __init__(
        self, reservations: ReservationRepository, stock: StockRepository, clock: Clock
    ) -> None:
        self._reservations = reservations
        self._stock = stock
        self._clock = clock

    async def __call__(self, event_id: UUID, product_id: UUID) -> None:
        await self._stock.lock(product_id)
        reservation = await self._reservations.get_active(event_id, product_id)
        if reservation is None:
            raise ReservationNotFoundError()
        reservation.release(self._clock.now())
        await self._reservations.save(reservation)


class ReleaseEventReservations:
    """Libera todo lo reservado de un evento al cancelarlo o finalizarlo (R-REC-3)."""

    def __init__(self, reservations: ReservationRepository, clock: Clock) -> None:
        self._reservations = reservations
        self._clock = clock

    async def __call__(self, event_id: UUID) -> None:
        await self._reservations.release_event(event_id, self._clock.now())
