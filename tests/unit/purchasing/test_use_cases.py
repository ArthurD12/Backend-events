"""Casos de uso de compras con piezas en memoria (HU27, HU28, HU29)."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from local_eventos.modules.purchasing.application.errors import (
    DocumentTakenError,
    PurchaseNotFoundError,
    SupplierInactiveError,
    SupplierNotFoundError,
)
from local_eventos.modules.purchasing.application.ports.repositories import PurchaseFilters
from local_eventos.modules.purchasing.application.use_cases.purchases import (
    CancelPurchase,
    CreatePurchaseRequest,
    GetPurchase,
    ListPurchases,
    OrderPurchase,
    PurchaseDetailsBuilder,
    PurchaseRequestCommand,
    ReceivePurchase,
    SuggestShortages,
)
from local_eventos.modules.purchasing.application.use_cases.suppliers import (
    CreateSupplier,
    ListSuppliers,
    SetSupplierActive,
    SupplierCommand,
    UpdateSupplier,
)
from local_eventos.modules.purchasing.domain.errors import (
    InvalidTransitionError,
    PurchasingValidationError,
)
from local_eventos.modules.purchasing.domain.purchase import Purchase, PurchaseStatus, ReceivedLine
from local_eventos.modules.purchasing.domain.supplier import DocumentType, Supplier
from tests.unit.inventory.fakes import FakeClock

from .fakes import FakeInventory, InMemoryPurchaseRepository, InMemorySupplierRepository

USER = uuid4()


@dataclass
class World:
    suppliers: InMemorySupplierRepository = field(default_factory=InMemorySupplierRepository)
    purchases: InMemoryPurchaseRepository = field(default_factory=InMemoryPurchaseRepository)
    inventory: FakeInventory = field(default_factory=FakeInventory)
    clock: FakeClock = field(default_factory=FakeClock)

    async def supplier(
        self, name: str = "Distribuidora Lima", number: str = "20123456789"
    ) -> Supplier:
        return await CreateSupplier(self.suppliers)(
            SupplierCommand(
                name=name, document_type=DocumentType.RUC, document_number=number, phone="987654321"
            )  # fmt: skip
        )

    async def request(self, *lines: tuple[UUID, str], event_id: UUID | None = None) -> Purchase:
        return await CreatePurchaseRequest(self.purchases, self.inventory.lookup, self.clock)(
            PurchaseRequestCommand(lines=[(p, Decimal(q)) for p, q in lines], event_id=event_id),
            created_by=USER,
        )

    async def order(self, purchase: Purchase, supplier: Supplier, cost: int = 400) -> Purchase:
        return await OrderPurchase(self.purchases, self.suppliers, self.clock)(
            purchase.id, supplier_id=supplier.id,
            unit_costs={line.product_id: cost for line in purchase.lines}, ordered_by=USER,
        )  # fmt: skip

    def receive(self) -> ReceivePurchase:
        return ReceivePurchase(self.purchases, self.inventory.receive, self.clock)

    def details(self) -> PurchaseDetailsBuilder:
        return PurchaseDetailsBuilder(self.inventory.lookup, self.suppliers)


async def test_ca27_documento_unico_busqueda_sin_tildes_y_desactivar() -> None:
    world = World()
    first = await world.supplier("Avícola Ñaña")
    await world.supplier("Bebidas del Sur", "20999999999")

    with pytest.raises(DocumentTakenError):
        await world.supplier("Otro", "20123456789")
    other = await world.supplier("Otro", "10456789012")
    with pytest.raises(DocumentTakenError):
        await UpdateSupplier(world.suppliers)(
            other.id,
            SupplierCommand(
                name="Otro",
                document_type=DocumentType.RUC,
                document_number="20999999999",
                phone="987654321",
            ),  # fmt: skip
        )
    assert [s.id for s in await ListSuppliers(world.suppliers)("avicola nana")] == [first.id]
    assert len(await ListSuppliers(world.suppliers)("2099")) == 1
    await SetSupplierActive(world.suppliers)(first.id, active=False)
    assert len(await ListSuppliers(world.suppliers)()) == 2
    assert len(await ListSuppliers(world.suppliers)(include_inactive=True)) == 3
    with pytest.raises(SupplierNotFoundError):
        await SetSupplierActive(world.suppliers)(uuid4(), active=True)


async def test_ca28_1_solicitud_con_codigo_correlativo_y_evento() -> None:
    world = World()
    sugar = world.inventory.add("AZU-01")
    event = uuid4()

    first = await world.request((sugar, "10"), event_id=event)
    second = await world.request((sugar, "1"))

    assert (first.code, second.code) == ("COM-2026-0001", "COM-2026-0002")
    assert first.event_id == event and first.status is PurchaseStatus.REQUESTED


async def test_ca28_1_producto_inexistente_o_inactivo_no_gasta_correlativo() -> None:
    world = World()
    off = world.inventory.add("OFF", active=False)

    for product in (off, uuid4()):
        with pytest.raises(PurchasingValidationError):
            await world.request((product, "1"))
    assert world.purchases.counters == {}


async def test_ca28_2_faltantes_para_volver_al_minimo() -> None:
    world = World()
    sugar = world.inventory.add("AZU-01")
    world.inventory.short(sugar, "2", "10")

    shortages = await SuggestShortages(world.inventory.low_stock)()

    assert [(s.product.code, s.suggested_quantity) for s in shortages] == [("AZU-01", 8)]


async def test_ca29_ordenar_recibir_y_entradas_con_costo_y_proveedor() -> None:
    world = World()
    sugar, oil = world.inventory.add("AZU-01"), world.inventory.add("ACE-01")
    supplier = await world.supplier()
    purchase = await world.order(await world.request((sugar, "10"), (oil, "5")), supplier, 400)

    received = await world.receive()(
        purchase.id,
        lines=[ReceivedLine(sugar, Decimal("9.5"), lot="L-1", expires_on=date(2027, 1, 1)),
               ReceivedLine(oil, Decimal(0))],
        received_by=USER, invoice_number="F001-77",
    )  # fmt: skip

    assert received.status is PurchaseStatus.RECEIVED and received.total_cents == 3800
    assert [(e.product_id, e.quantity, e.unit_cost_cents, e.supplier_id, e.lot, e.purchase_id)
            for e in world.inventory.received] == [
        (sugar, Decimal("9.5"), 400, supplier.id, "L-1", purchase.id)
    ]  # fmt: skip
    assert purchase.id in world.purchases.locked
    with pytest.raises(InvalidTransitionError):
        await world.receive()(purchase.id, lines=[ReceivedLine(sugar, Decimal(1)),
                              ReceivedLine(oil, Decimal(1))], received_by=USER)  # fmt: skip
    assert len(world.inventory.received) == 1


async def test_ca29_proveedor_inactivo_no_recibe_ordenes() -> None:
    world = World()
    sugar = world.inventory.add("AZU-01")
    supplier = await world.supplier()
    await SetSupplierActive(world.suppliers)(supplier.id, active=False)
    purchase = await world.request((sugar, "1"))

    with pytest.raises(SupplierInactiveError):
        await world.order(purchase, supplier)
    with pytest.raises(SupplierNotFoundError):
        await OrderPurchase(world.purchases, world.suppliers, world.clock)(
            purchase.id, supplier_id=uuid4(), unit_costs={sugar: 1}, ordered_by=USER
        )


async def test_cancelar_consultar_y_listar() -> None:
    world = World()
    sugar = world.inventory.add("AZU-01")
    supplier = await world.supplier()
    kept = await world.order(await world.request((sugar, "1")), supplier)
    dropped = await world.request((sugar, "2"))

    await CancelPurchase(world.purchases, world.clock)(
        dropped.id, reason="Duplicada", cancelled_by=USER
    )
    detail = await GetPurchase(world.purchases, world.details())(kept.id)
    page = await ListPurchases(world.purchases, world.details())(
        PurchaseFilters(status=PurchaseStatus.CANCELLED)
    )

    assert detail.supplier is not None and detail.supplier.id == supplier.id
    assert detail.products[sugar].code == "AZU-01"
    assert [d.purchase.code for d in page.items] == [dropped.code] and page.total == 1
    with pytest.raises(PurchaseNotFoundError):
        await GetPurchase(world.purchases, world.details())(uuid4())
