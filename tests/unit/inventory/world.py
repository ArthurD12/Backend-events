"""Inventario armado en memoria para las pruebas de casos de uso."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from local_eventos.modules.inventory.application.use_cases.event_materials import (
    GetEventMaterials,
)
from local_eventos.modules.inventory.application.use_cases.movements import (
    MovementCommand,
    RecordedMovement,
    RecordMovement,
)
from local_eventos.modules.inventory.application.use_cases.products import (
    CreateProduct,
    GetProduct,
    ListProducts,
    ProductCommand,
    ProductViews,
)
from local_eventos.modules.inventory.domain.movement import MovementKind
from local_eventos.modules.inventory.domain.product import Category, Product, ProductKind, Unit

from .fakes import (
    FakeClock,
    FakeEventLookup,
    InMemoryMovementRepository,
    InMemoryProductRepository,
    InMemoryReservationRepository,
    InMemoryStockRepository,
)


@dataclass
class World:
    products: InMemoryProductRepository = field(default_factory=InMemoryProductRepository)
    stock: InMemoryStockRepository = field(default_factory=InMemoryStockRepository)
    movements: InMemoryMovementRepository = field(default_factory=InMemoryMovementRepository)
    events: FakeEventLookup = field(default_factory=FakeEventLookup)
    reservations: InMemoryReservationRepository = field(
        default_factory=InMemoryReservationRepository
    )
    clock: FakeClock = field(default_factory=FakeClock)
    user: UUID = field(default_factory=uuid4)

    def record(self) -> RecordMovement:
        return RecordMovement(
            self.products, self.stock, self.movements, self.events, self.reservations, self.clock
        )

    def views(self) -> ProductViews:
        return ProductViews(self.stock, self.movements, self.clock)

    def list(self) -> ListProducts:
        return ListProducts(self.products, self.views())

    def get(self) -> GetProduct:
        return GetProduct(self.products, self.views())

    def materials(self) -> GetEventMaterials:
        return GetEventMaterials(self.products, self.movements, self.events)

    async def product(self, code: str = "PLA-01", **changes: Any) -> Product:
        data: dict[str, Any] = {
            "code": code,
            "name": "Plato llano",
            "category": Category.DINNERWARE,
            "unit": Unit.UNIT,
            "kind": ProductKind.REUSABLE,
            "min_stock": Decimal(10),
            **changes,
        }
        return await CreateProduct(self.products)(ProductCommand(**data))

    async def move(
        self, kind: MovementKind, product: Product, quantity: str, **extra: Any
    ) -> RecordedMovement:
        command = MovementCommand(
            kind=kind, product_id=product.id, quantity=Decimal(quantity), **extra
        )
        return await self.record()(command, recorded_by=self.user)

    async def entry(self, product: Product, quantity: str, cost: int = 100, **extra: Any) -> None:
        await self.move(MovementKind.ENTRY, product, quantity, unit_cost_cents=cost, **extra)
