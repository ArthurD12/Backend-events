"""Fakes de las consultas que usan los reportes y el panel (020). Sin base de datos."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from local_eventos.modules.commercial.public_api import (
    EventRefs,
    EventReportFilters,
    EventReportItem,
    EventStatus,
    EventType,
    Receivables,
)
from local_eventos.modules.inventory.public_api import (
    Category,
    MovementItem,
    MovementKind,
    ProductInfo,
    ProductKind,
    StockItem,
    Unit,
)
from local_eventos.modules.ledger.public_api import (
    CashEntry,
    CashEntryKind,
    MovementCategory,
    PaymentKind,
)
from local_eventos.modules.purchasing.public_api import (
    OpenPurchases,
    PurchaseReportItem,
    PurchaseStatus,
)

NOW = datetime(2026, 11, 25, 15, 30, tzinfo=UTC)  # 10:30 en Lima
EVENT_ID, CONTRACT_ID, OTHER_CONTRACT = uuid4(), uuid4(), uuid4()


class FixedClock:
    def now(self) -> datetime:
        return NOW


def event_item(
    code: str = "EVT-2026-0001",
    status: EventStatus = EventStatus.SCHEDULED,
    total: int = 1_000_000,
    paid: int = 500_000,
) -> EventReportItem:
    return EventReportItem(
        id=EVENT_ID, code=code, event_date=date(2026, 12, 19), client_name="José Ramírez",
        event_type=EventType.WEDDING, guests=120, status=status, contract_id=CONTRACT_ID,
        total_cents=total, paid_cents=paid, balance_cents=total - paid, overdue=False,
    )  # fmt: skip


class FakeEvents:
    def __init__(self, *items: EventReportItem) -> None:
        self.items = list(items) or [event_item(), event_item("EVT-2026-0002", total=200_000)]
        self.filters: list[EventReportFilters] = []

    async def __call__(self, filters: EventReportFilters) -> list[EventReportItem]:
        self.filters.append(filters)
        return self.items


async def upcoming(days: int = 14) -> list[EventReportItem]:
    return [event_item()]


async def receivables() -> Receivables:
    return Receivables(total_cents=700_000, contracts=2, overdue_contracts=1, overdue_cents=200_000)


def cash_entry(
    kind: CashEntryKind, amount: int, *, voided: bool = False, day: int = 5
) -> CashEntry:
    is_payment = kind in (CashEntryKind.CLIENT_PAYMENT, CashEntryKind.REFUND)
    return CashEntry(
        occurred_on=date(2026, 11, day),
        kind=kind,
        category=None if is_payment else (
            MovementCategory.OTHER_INCOME if kind is CashEntryKind.INCOME
            else MovementCategory.STAFF
        ),
        payment_kind=(PaymentKind.REFUND if kind is CashEntryKind.REFUND
                      else PaymentKind.ADVANCE) if is_payment else None,
        concept="PAG-2026-0001" if is_payment else "Mozos",
        amount_cents=amount,
        contract_id=CONTRACT_ID if is_payment else None,
        event_id=None if is_payment else EVENT_ID,
        voided=voided,
    )  # fmt: skip


async def cash_entries(date_from: date, date_to: date) -> list[CashEntry]:
    return [
        cash_entry(CashEntryKind.CLIENT_PAYMENT, 500_000),
        cash_entry(CashEntryKind.CLIENT_PAYMENT, 90_000, voided=True, day=6),
        cash_entry(CashEntryKind.REFUND, 10_000, day=7),
        cash_entry(CashEntryKind.INCOME, 30_000, day=8),
        cash_entry(CashEntryKind.EXPENSE, 120_000, day=9),
    ]


async def event_refs(event_ids: list[UUID], contract_ids: list[UUID]) -> EventRefs:
    return EventRefs(
        by_event={EVENT_ID: "EVT-2026-0001"} if EVENT_ID in event_ids else {},
        by_contract={CONTRACT_ID: "EVT-2026-0001"} if CONTRACT_ID in contract_ids else {},
    )


PLATE = ProductInfo(
    id=uuid4(), code="PLA-01", name="Plato llano", unit=Unit.UNIT,
    kind=ProductKind.REUSABLE, active=True,
)  # fmt: skip
MILK = ProductInfo(
    id=uuid4(), code="LEC-01", name="Leche", unit=Unit.LITER,
    kind=ProductKind.CONSUMABLE, active=True,
)  # fmt: skip


async def stock(
    category: Category | None = None, *, include_inactive: bool = False
) -> list[StockItem]:
    return [
        StockItem(product=PLATE, category=Category.DINNERWARE, min_stock=Decimal(10),
                  stock=Decimal("8.000"), avg_cost_cents=500, value_cents=4_000,
                  is_low_stock=True, next_expiry=None, expiring_soon=False),
        StockItem(product=MILK, category=Category.BEVERAGES, min_stock=Decimal(1),
                  stock=Decimal("4.500"), avg_cost_cents=350, value_cents=1_575,
                  is_low_stock=False, next_expiry=date(2026, 12, 5), expiring_soon=True),
    ]  # fmt: skip


async def movements(
    date_from: date, date_to: date, kind: MovementKind | None = None
) -> list[MovementItem]:
    return [
        MovementItem(occurred_on=date(2026, 11, 3), product=PLATE, kind=MovementKind.ENTRY,
                     quantity=Decimal("10.000"), unit_cost_cents=500, event_id=None,
                     lot="L-1", reason=None),
        MovementItem(occurred_on=date(2026, 11, 4), product=PLATE, kind=MovementKind.EXIT,
                     quantity=Decimal("2.000"), unit_cost_cents=None, event_id=EVENT_ID,
                     lot=None, reason=None),
    ]  # fmt: skip


async def purchases(
    date_from: date, date_to: date, status: PurchaseStatus | None = None
) -> list[PurchaseReportItem]:
    return [
        PurchaseReportItem(id=uuid4(), code="COM-2026-0001", created_on=date(2026, 11, 2),
                           supplier_name="Distribuidora Lima", status=PurchaseStatus.RECEIVED,
                           total_cents=4_000, received_on=date(2026, 11, 3), event_id=EVENT_ID),
        PurchaseReportItem(id=uuid4(), code="COM-2026-0002", created_on=date(2026, 11, 4),
                           supplier_name=None, status=PurchaseStatus.CANCELLED,
                           total_cents=1_000, received_on=None, event_id=None),
    ]  # fmt: skip


async def open_purchases() -> OpenPurchases:
    return OpenPurchases(requested=2, ordered=1)
