"""Requerimiento de materiales de un evento (HU25): se calcula al momento (R-REC-2)."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from local_eventos.modules.commercial.public_api import (
    EventDetailLookup,
    EventServiceInfo,
    EventStatus,
    LineKind,
)
from local_eventos.modules.inventory.application.ports.product_repository import (
    ProductRepository,
)
from local_eventos.modules.inventory.application.ports.recipe_repository import RecipeRepository
from local_eventos.modules.inventory.application.ports.reservation_repository import (
    ReservationRepository,
)
from local_eventos.modules.inventory.application.ports.stock_repository import (
    MovementRepository,
    StockRepository,
)
from local_eventos.modules.inventory.application.use_cases.lookups import (
    ProductInfo,
    product_info,
)
from local_eventos.modules.inventory.domain.event_materials import EventMaterials
from local_eventos.modules.inventory.domain.quantity import ZERO
from local_eventos.modules.inventory.domain.requirement import (
    ContractedService,
    required_materials,
    shortage,
)

_CALCULABLE = (EventStatus.SCHEDULED, EventStatus.CONFIRMED, EventStatus.IN_PROGRESS)


@dataclass(frozen=True)
class RequirementLine:
    product: ProductInfo
    required: Decimal
    out: Decimal  # ya salió para el evento
    reserved: Decimal  # apartado para el evento
    available: Decimal  # libre en almacén (stock menos todas las reservas vigentes)
    shortage: Decimal  # lo que falta comprar (≥ 0)


@dataclass(frozen=True)
class EventRequirement:
    event_id: UUID
    event_code: str
    status: EventStatus
    calculated: bool  # falso en eventos finalizados o cancelados (R-REC-2)
    guests: int
    lines: list[RequirementLine]
    without_recipe: list[str]  # servicios sin insumos definidos (CA-25.3)


class GetEventRequirement:
    def __init__(
        self,
        events: EventDetailLookup,
        recipes: RecipeRepository,
        products: ProductRepository,
        stock: StockRepository,
        movements: MovementRepository,
        reservations: ReservationRepository,
    ) -> None:
        self._events = events
        self._recipes = recipes
        self._products = products
        self._stock = stock
        self._movements = movements
        self._reservations = reservations

    async def __call__(self, event_id: UUID) -> EventRequirement | None:
        """`None` si el evento no existe."""
        event = await self._events(event_id)
        if event is None:
            return None
        if event.status not in _CALCULABLE:
            return EventRequirement(event.id, event.code, event.status, False, event.guests, [], [])
        services = _contracted(event.services)
        recipes = await self._recipes.get_many([s.service_id for s in services])
        needed = required_materials(services, recipes, event.guests)
        ids = list(needed.by_product)
        found = {p.id: p for p in await self._products.get_many(ids)}
        levels = await self._stock.get_many(ids)
        reserved_all = await self._reservations.active_totals(ids)
        own = {
            r.product_id: r.quantity for r in await self._reservations.active_for_event(event_id)
        }
        movements = await self._movements.list_for_event(event_id)
        lines = []
        for product_id, required in needed.by_product.items():
            product = found.get(product_id)
            if product is None:
                continue
            stock = levels[product_id].quantity if product_id in levels else ZERO
            available = max(ZERO, stock - reserved_all.get(product_id, ZERO))
            out = EventMaterials.from_movements(product.id, product.kind, movements).out
            reserved = own.get(product_id, ZERO)
            lines.append(
                RequirementLine(
                    product=product_info(product),
                    required=required,
                    out=out,
                    reserved=reserved,
                    available=available,
                    shortage=shortage(required, out, reserved, available),
                )
            )
        lines.sort(key=lambda line: line.product.name.lower())
        return EventRequirement(
            event.id, event.code, event.status, True, event.guests, lines, needed.without_recipe
        )


def _contracted(services: tuple[EventServiceInfo, ...]) -> list[ContractedService]:
    """Agrupa por servicio del catálogo; los conceptos libres (EXTRA) no llevan insumos."""
    grouped: dict[UUID, ContractedService] = {}
    for item in services:
        if item.kind is not LineKind.SERVICE or item.service_id is None:
            continue
        current = grouped.get(item.service_id)
        grouped[item.service_id] = ContractedService(
            item.service_id, item.description, item.quantity + (current.quantity if current else 0)
        )
    return list(grouped.values())
