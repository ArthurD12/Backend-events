"""Caso de uso: materiales de un evento (HU26, CA-26.6)."""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.commercial.public_api import EventLookup
from local_eventos.modules.inventory.application.errors import EventNotFoundError
from local_eventos.modules.inventory.application.ports.product_repository import (
    ProductRepository,
)
from local_eventos.modules.inventory.application.ports.stock_repository import (
    MovementRepository,
)
from local_eventos.modules.inventory.domain.event_materials import EventMaterials
from local_eventos.modules.inventory.domain.product import Product


@dataclass(frozen=True)
class EventMaterialLine:
    product: Product
    materials: EventMaterials


class GetEventMaterials:
    def __init__(
        self, products: ProductRepository, movements: MovementRepository, events: EventLookup
    ) -> None:
        self._products = products
        self._movements = movements
        self._events = events

    async def __call__(self, event_id: UUID) -> list[EventMaterialLine]:
        """Por producto, ordenado por nombre: salió, volvió, merma y falta devolver."""
        if await self._events(event_id) is None:
            raise EventNotFoundError()
        movements = await self._movements.list_for_event(event_id)
        ids = list(dict.fromkeys(m.product_id for m in movements))
        products = await self._products.get_many(ids)
        lines = [
            EventMaterialLine(p, EventMaterials.from_movements(p.id, p.kind, movements))
            for p in products
        ]
        return sorted(lines, key=lambda line: line.product.name.lower())
