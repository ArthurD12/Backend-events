"""Piezas de inventario en memoria para probar sin base de datos."""

from dataclasses import replace
from datetime import UTC, date, datetime, time
from uuid import UUID, uuid4

from local_eventos.modules.catalog.public_api import ServiceSummary
from local_eventos.modules.commercial.public_api import EventInfo, EventStatus
from local_eventos.modules.inventory.application.errors import CodeTakenError
from local_eventos.modules.inventory.application.ports.product_repository import ProductFilters
from local_eventos.modules.inventory.application.search_text import normalize
from local_eventos.modules.inventory.domain.movement import Movement, MovementKind
from local_eventos.modules.inventory.domain.product import Product
from local_eventos.modules.inventory.domain.recipe import RecipeLine
from local_eventos.modules.inventory.domain.stock import StockLevel

TODAY = date(2026, 11, 25)
NOW = datetime(2026, 11, 25, 15, tzinfo=UTC)


class FakeClock:
    def __init__(self, today: date = TODAY) -> None:
        self.day = today

    def now(self) -> datetime:
        return NOW

    def today(self) -> date:
        return self.day


class InMemoryProductRepository:
    def __init__(self) -> None:
        self.products: dict[UUID, Product] = {}

    async def get(self, product_id: UUID) -> Product | None:
        product = self.products.get(product_id)
        return replace(product) if product else None

    async def get_many(self, product_ids: list[UUID]) -> list[Product]:
        return [replace(self.products[i]) for i in product_ids if i in self.products]

    async def get_by_code(self, code: str) -> Product | None:
        return next((replace(p) for p in self.products.values() if p.code == code), None)

    async def add(self, product: Product) -> None:
        if any(p.code == product.code for p in self.products.values()):
            raise CodeTakenError()
        self.products[product.id] = replace(product)

    async def update(self, product: Product) -> None:
        self.products[product.id] = replace(product)

    async def search(self, filters: ProductFilters, *, limit: int) -> list[Product]:
        text = normalize(filters.text)
        found = [
            replace(p)
            for p in self.products.values()
            if (filters.include_inactive or p.active)
            and (filters.category is None or p.category is filters.category)
            and (not text or text in normalize(p.name) or text in p.code.lower())
        ]
        return sorted(found, key=lambda p: p.name.lower())[:limit]


class InMemoryStockRepository:
    def __init__(self) -> None:
        self.levels: dict[UUID, StockLevel] = {}
        self.locked: list[UUID] = []

    async def lock(self, product_id: UUID) -> StockLevel:
        self.locked.append(product_id)
        return self.levels.get(product_id, StockLevel(product_id))

    async def save(self, level: StockLevel) -> None:
        self.levels[level.product_id] = level

    async def get_many(self, product_ids: list[UUID]) -> dict[UUID, StockLevel]:
        return {i: self.levels[i] for i in product_ids if i in self.levels}


class InMemoryMovementRepository:
    def __init__(self) -> None:
        self.movements: list[Movement] = []

    async def add(self, movement: Movement) -> None:
        self.movements.append(movement)

    async def list_for_product(
        self, product_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Movement], int]:
        found = [m for m in reversed(self.movements) if m.product_id == product_id]
        return found[offset : offset + limit], len(found)

    async def list_for_event(
        self, event_id: UUID, product_id: UUID | None = None
    ) -> list[Movement]:
        return [
            m
            for m in self.movements
            if m.event_id == event_id and (product_id is None or m.product_id == product_id)
        ]

    async def list_between(
        self, date_from: date, date_to: date, kind: MovementKind | None = None
    ) -> list[Movement]:
        return [
            m
            for m in sorted(self.movements, key=lambda m: (m.occurred_on, m.recorded_at))
            if date_from <= m.occurred_on <= date_to and (kind is None or m.kind is kind)
        ]

    async def entries_for(self, product_ids: list[UUID]) -> list[Movement]:
        return [
            m
            for m in self.movements
            if m.kind is MovementKind.ENTRY and m.product_id in product_ids
        ]


class FakeEventLookup:
    def __init__(self) -> None:
        self.events: dict[UUID, EventInfo] = {}

    def add(self, status: EventStatus = EventStatus.SCHEDULED) -> UUID:
        event_id = uuid4()
        self.events[event_id] = EventInfo(
            id=event_id,
            code=f"EVT-2026-{len(self.events) + 1:04d}",
            status=status,
            event_date=date(2026, 12, 19),
            start_time=time(20),
            end_time=time(3),
        )
        return event_id

    async def __call__(self, event_id: UUID) -> EventInfo | None:
        return self.events.get(event_id)


class InMemoryRecipeRepository:
    def __init__(self) -> None:
        self.recipes: dict[UUID, list[RecipeLine]] = {}

    async def get(self, service_id: UUID) -> list[RecipeLine]:
        return list(self.recipes.get(service_id, []))

    async def get_many(self, service_ids: list[UUID]) -> dict[UUID, list[RecipeLine]]:
        return {i: list(self.recipes[i]) for i in service_ids if self.recipes.get(i)}

    async def replace(self, service_id: UUID, lines: list[RecipeLine]) -> None:
        self.recipes[service_id] = list(lines)


class FakeServiceLookup:
    def __init__(self) -> None:
        self.services: dict[UUID, ServiceSummary] = {}

    def add(self, name: str = "Menú criollo") -> UUID:
        service_id = uuid4()
        self.services[service_id] = ServiceSummary(
            id=service_id,
            name=name,
            category_id=uuid4(),
            price_unit="PER_PERSON",
            reference_price_cents=5000,
            currency="PEN",
            active=True,
        )
        return service_id

    async def __call__(self, service_id: UUID) -> ServiceSummary | None:
        return self.services.get(service_id)
