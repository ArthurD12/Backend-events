"""Casos de uso de compras (HU28, HU29): solicitar, sugerir faltantes, ordenar, recibir y cancelar.

Recibir registra las entradas de almacén por `inventory.public_api.stock_receiver` dentro de la
misma transacción: o queda la compra recibida con sus entradas, o nada (CA-29.2).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from local_eventos.modules.inventory.public_api import (
    LowStockLookup,
    ProductInfo,
    ProductLookup,
    StockEntry,
    StockReceiver,
)
from local_eventos.modules.purchasing.application.errors import (
    PurchaseNotFoundError,
    SupplierInactiveError,
)
from local_eventos.modules.purchasing.application.ports.clock import Clock
from local_eventos.modules.purchasing.application.ports.repositories import (
    PurchaseFilters,
    PurchaseRepository,
    SupplierRepository,
)
from local_eventos.modules.purchasing.application.use_cases.suppliers import GetSupplier
from local_eventos.modules.purchasing.domain.errors import PurchasingValidationError
from local_eventos.modules.purchasing.domain.purchase import (
    Purchase,
    ReceivedLine,
    format_purchase_code,
)
from local_eventos.modules.purchasing.domain.supplier import Supplier

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class PurchaseRequestCommand:
    lines: list[tuple[UUID, Decimal]]
    event_id: UUID | None = None
    notes: str | None = None


@dataclass(frozen=True)
class Shortage:
    """CA-28.2: producto con stock bajo y cuánto pedir para volver al mínimo."""

    product: ProductInfo
    stock: Decimal
    min_stock: Decimal
    suggested_quantity: Decimal


@dataclass(frozen=True)
class PurchaseDetails:
    """La compra con los datos de sus productos y su proveedor, para mostrarla."""

    purchase: Purchase
    products: dict[UUID, ProductInfo]
    supplier: Supplier | None


@dataclass(frozen=True)
class PurchasePage:
    items: list[PurchaseDetails]
    total: int
    page: int
    page_size: int


class PurchaseDetailsBuilder:
    def __init__(self, products: ProductLookup, suppliers: SupplierRepository) -> None:
        self._products = products
        self._suppliers = suppliers

    async def __call__(self, purchases: list[Purchase]) -> list[PurchaseDetails]:
        product_ids = {line.product_id for p in purchases for line in p.lines}
        products = {}
        for product_id in product_ids:
            info = await self._products(product_id)
            if info is not None:
                products[product_id] = info
        supplier_ids = list({p.supplier_id for p in purchases if p.supplier_id})
        suppliers = {s.id: s for s in await self._suppliers.get_many(supplier_ids)}
        return [
            PurchaseDetails(
                purchase=p,
                products={
                    line.product_id: products[line.product_id]
                    for line in p.lines
                    if line.product_id in products
                },
                supplier=suppliers.get(p.supplier_id) if p.supplier_id else None,
            )  # fmt: skip
            for p in purchases
        ]


class CreatePurchaseRequest:
    def __init__(
        self, purchases: PurchaseRepository, products: ProductLookup, clock: Clock
    ) -> None:
        self._purchases = purchases
        self._products = products
        self._clock = clock

    async def __call__(self, command: PurchaseRequestCommand, *, created_by: UUID) -> Purchase:
        """CA-28.1. Los productos deben existir y estar activos."""
        now, today = self._clock.now(), self._clock.today()
        # Valida con código provisional: si algo falla, no se gasta un correlativo.
        Purchase.request(
            code="", lines=command.lines, created_by=created_by, now=now,
            event_id=command.event_id, notes=command.notes,
        )  # fmt: skip
        for product_id, _ in command.lines:
            info = await self._products(product_id)
            if info is None or not info.active:
                raise PurchasingValidationError("Un producto no existe o está desactivado.")
        number = await self._purchases.next_number(today.year)
        purchase = Purchase.request(
            code=format_purchase_code(today.year, number), lines=command.lines,
            created_by=created_by, now=now, event_id=command.event_id, notes=command.notes,
        )  # fmt: skip
        await self._purchases.add(purchase)
        return purchase


class SuggestShortages:
    def __init__(self, low_stock: LowStockLookup) -> None:
        self._low_stock = low_stock

    async def __call__(self) -> list[Shortage]:
        """CA-28.2: propuesta editable; el cálculo por menú e invitados llega con HU24–HU25."""
        return [
            Shortage(
                product=item.product,
                stock=item.stock,
                min_stock=item.min_stock,
                suggested_quantity=item.shortage,
            )
            for item in await self._low_stock()
        ]


class OrderPurchase:
    def __init__(
        self, purchases: PurchaseRepository, suppliers: SupplierRepository, clock: Clock
    ) -> None:
        self._purchases = purchases
        self._suppliers = suppliers
        self._clock = clock

    async def __call__(
        self,
        purchase_id: UUID,
        *,
        supplier_id: UUID,
        unit_costs: dict[UUID, int],
        ordered_by: UUID,
    ) -> Purchase:
        purchase = await _get(self._purchases, purchase_id, for_update=True)
        supplier = await GetSupplier(self._suppliers)(supplier_id)
        if not supplier.active:
            raise SupplierInactiveError()
        purchase.order(
            supplier_id=supplier.id,
            unit_costs=unit_costs,
            ordered_by=ordered_by,
            now=self._clock.now(),
        )
        await self._purchases.update(purchase)
        return purchase


class ReceivePurchase:
    def __init__(
        self, purchases: PurchaseRepository, receiver: StockReceiver, clock: Clock
    ) -> None:
        self._purchases = purchases
        self._receiver = receiver
        self._clock = clock

    async def __call__(
        self,
        purchase_id: UUID,
        *,
        lines: list[ReceivedLine],
        received_by: UUID,
        invoice_number: str | None = None,
        received_on: date | None = None,
    ) -> Purchase:
        """CA-29.2: genera las entradas con su costo y proveedor. Solo entonces sube el stock.

        La compra se bloquea: dos recepciones simultáneas no duplican las entradas (CA-29.3).
        """
        purchase = await _get(self._purchases, purchase_id, for_update=True)
        purchase.receive(
            lines=lines,
            received_by=received_by,
            now=self._clock.now(),
            invoice_number=invoice_number,
        )
        await self._purchases.update(purchase)
        await self._receiver(
            [
                StockEntry(
                    product_id=line.product_id,
                    quantity=line.received_quantity,
                    unit_cost_cents=line.unit_cost_cents or 0,
                    supplier_id=purchase.supplier_id,
                    lot=line.lot,
                    expires_on=line.expires_on,
                    purchase_id=purchase.id,
                    occurred_on=received_on,
                )
                for line in purchase.lines
                if line.received_quantity
            ],
            recorded_by=received_by,
        )
        return purchase


class CancelPurchase:
    def __init__(self, purchases: PurchaseRepository, clock: Clock) -> None:
        self._purchases = purchases
        self._clock = clock

    async def __call__(self, purchase_id: UUID, *, reason: str, cancelled_by: UUID) -> Purchase:
        purchase = await _get(self._purchases, purchase_id, for_update=True)
        purchase.cancel(reason=reason, cancelled_by=cancelled_by, now=self._clock.now())
        await self._purchases.update(purchase)
        return purchase


class GetPurchase:
    def __init__(self, purchases: PurchaseRepository, details: PurchaseDetailsBuilder) -> None:
        self._purchases = purchases
        self._details = details

    async def __call__(self, purchase_id: UUID) -> PurchaseDetails:
        return (await self._details([await _get(self._purchases, purchase_id)]))[0]


class ListPurchases:
    def __init__(self, purchases: PurchaseRepository, details: PurchaseDetailsBuilder) -> None:
        self._purchases = purchases
        self._details = details

    async def __call__(
        self, filters: PurchaseFilters, *, page: int = 1, page_size: int = 20
    ) -> PurchasePage:
        page = max(page, 1)
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        items, total = await self._purchases.search(
            filters, limit=page_size, offset=(page - 1) * page_size
        )
        return PurchasePage(await self._details(items), total, page, page_size)


async def _get(
    purchases: PurchaseRepository, purchase_id: UUID, *, for_update: bool = False
) -> Purchase:
    purchase = await purchases.get(purchase_id, for_update=for_update)
    if purchase is None:
        raise PurchaseNotFoundError()
    return purchase
