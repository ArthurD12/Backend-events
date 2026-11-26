"""Proveedores, compras e inventario de mentira para probar compras sin base de datos."""

from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid4

from local_eventos.modules.inventory.public_api import (
    LowStockItem,
    ProductInfo,
    ProductKind,
    RecordedMovement,
    StockEntry,
    Unit,
)
from local_eventos.modules.purchasing.application.errors import DocumentTakenError
from local_eventos.modules.purchasing.application.ports.repositories import PurchaseFilters
from local_eventos.modules.purchasing.application.search_text import normalize
from local_eventos.modules.purchasing.domain.purchase import Purchase, PurchaseStatus
from local_eventos.modules.purchasing.domain.supplier import DocumentType, Supplier


class InMemorySupplierRepository:
    def __init__(self) -> None:
        self.suppliers: dict[UUID, Supplier] = {}

    async def get(self, supplier_id: UUID) -> Supplier | None:
        found = self.suppliers.get(supplier_id)
        return replace(found) if found else None

    async def get_many(self, supplier_ids: list[UUID]) -> list[Supplier]:
        return [replace(self.suppliers[i]) for i in supplier_ids if i in self.suppliers]

    async def get_by_document(self, document_type: DocumentType, number: str) -> Supplier | None:
        return next(
            (
                replace(s)
                for s in self.suppliers.values()
                if s.document_type is document_type and s.document_number == number
            ),
            None,
        )

    async def add(self, supplier: Supplier) -> None:
        if await self.get_by_document(supplier.document_type, supplier.document_number):
            raise DocumentTakenError()
        self.suppliers[supplier.id] = replace(supplier)

    async def update(self, supplier: Supplier) -> None:
        self.suppliers[supplier.id] = replace(supplier)

    async def search(self, text: str, *, include_inactive: bool, limit: int) -> list[Supplier]:
        needle = normalize(text)
        found = [
            replace(s)
            for s in self.suppliers.values()
            if (include_inactive or s.active)
            and (not needle or needle in normalize(s.name) or needle in s.document_number)
        ]
        return sorted(found, key=lambda s: s.name.lower())[:limit]


class InMemoryPurchaseRepository:
    def __init__(self) -> None:
        self.purchases: dict[UUID, Purchase] = {}
        self.counters: dict[int, int] = {}
        self.locked: list[UUID] = []

    async def get(self, purchase_id: UUID, *, for_update: bool = False) -> Purchase | None:
        if for_update:
            self.locked.append(purchase_id)
        found = self.purchases.get(purchase_id)
        return replace(found) if found else None

    async def add(self, purchase: Purchase) -> None:
        self.purchases[purchase.id] = replace(purchase)

    async def update(self, purchase: Purchase) -> None:
        self.purchases[purchase.id] = replace(purchase)

    async def next_number(self, year: int) -> int:
        self.counters[year] = self.counters.get(year, 0) + 1
        return self.counters[year]

    async def search(
        self, filters: PurchaseFilters, *, limit: int, offset: int
    ) -> tuple[list[Purchase], int]:
        found = [
            replace(p)
            for p in sorted(self.purchases.values(), key=lambda p: p.code, reverse=True)
            if (filters.status is None or p.status is filters.status)
            and (filters.event_id is None or p.event_id == filters.event_id)
            and (filters.supplier_id is None or p.supplier_id == filters.supplier_id)
            and (filters.created_from is None or p.created.at >= filters.created_from)
            and (filters.created_before is None or p.created.at < filters.created_before)
        ]
        return found[offset : offset + limit], len(found)

    async def count_by_status(self) -> dict[PurchaseStatus, int]:
        counts: dict[PurchaseStatus, int] = {}
        for p in self.purchases.values():
            counts[p.status] = counts.get(p.status, 0) + 1
        return counts


class FakeInventory:
    """Hace de `inventory.public_api`: productos, faltantes y receptor de entradas."""

    def __init__(self) -> None:
        self.products: dict[UUID, ProductInfo] = {}
        self.low: list[LowStockItem] = []
        self.received: list[StockEntry] = []

    def add(self, code: str, *, active: bool = True) -> UUID:
        product_id = uuid4()
        self.products[product_id] = ProductInfo(
            id=product_id, code=code, name=f"Producto {code}", unit=Unit.KG,
            kind=ProductKind.CONSUMABLE, active=active,
        )  # fmt: skip
        return product_id

    def short(self, product_id: UUID, stock: str, minimum: str) -> None:
        self.low.append(
            LowStockItem(
                product=self.products[product_id],
                stock=Decimal(stock),
                min_stock=Decimal(minimum),
                shortage=Decimal(minimum) - Decimal(stock),
            )  # fmt: skip
        )

    async def lookup(self, product_id: UUID) -> ProductInfo | None:
        return self.products.get(product_id)

    async def low_stock(self) -> list[LowStockItem]:
        return list(self.low)

    async def receive(
        self, entries: list[StockEntry], *, recorded_by: UUID
    ) -> list[RecordedMovement]:
        self.received.extend(entries)
        return []
