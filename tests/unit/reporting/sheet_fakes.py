"""Fakes de cada lookup que usa la ficha del evento (019). Sin base de datos."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID, uuid4

from local_eventos.modules.commercial.public_api import (
    AccountPaymentInfo,
    ActivityInfo,
    ActivityStatus,
    ClientSummary,
    ContractStatus,
    EventAccount,
    EventDetail,
    EventFollowUp,
    EventServiceInfo,
    EventStatus,
    EventType,
    LineKind,
    LineUnit,
    NoteInfo,
)
from local_eventos.modules.inventory.public_api import (
    EventMaterialInfo,
    ProductInfo,
    ProductKind,
    Unit,
)
from local_eventos.modules.ledger.public_api import PaymentKind, PaymentMethod
from local_eventos.modules.reporting.application.ports.event_staff import StaffAssignment
from local_eventos.modules.staff.public_api import WorkerFunction

EVENT_ID = uuid4()
COORDINATOR = uuid4()
AUTHOR = uuid4()
NOW = datetime(2026, 11, 25, 15, tzinfo=UTC)

DETAIL = EventDetail(
    id=EVENT_ID, code="EVT-2026-0001", status=EventStatus.CONFIRMED,
    event_type=EventType.WEDDING, event_date=date(2026, 12, 19), start_time=time(20),
    end_time=time(3), ends_next_day=True, venue="Local Los Jardines", guests=120,
    coordinator_id=COORDINATOR, contract_id=uuid4(),
    client=ClientSummary(id=uuid4(), name="José Ramírez", document_type="DNI",
                         document_number="40000001", phone="987654321", email=None,
                         active=True),
    services=(EventServiceInfo(LineKind.SERVICE, uuid4(), "Buffet criollo",
                               LineUnit.PER_PERSON, 120),),
)  # fmt: skip

FOLLOW_UP = EventFollowUp(
    activities=[
        ActivityInfo(uuid4(), "Probar menú", ActivityStatus.DONE, COORDINATOR, NOW, NOW),
        ActivityInfo(uuid4(), "Confirmar mozos", ActivityStatus.PENDING, COORDINATOR, NOW, None),
    ],
    recent_notes=[NoteInfo(uuid4(), "Faltan 20 copas", AUTHOR, NOW, None)],
)

MATERIALS = [
    EventMaterialInfo(
        product=ProductInfo(uuid4(), "PLA-01", "Plato llano", Unit.UNIT, ProductKind.REUSABLE,
                            True),
        out=Decimal(50), returned=Decimal(45), wasted=Decimal(1), pending_return=Decimal(4),
    )
]  # fmt: skip

ACCOUNT = EventAccount(
    contract_id=DETAIL.contract_id, contract_code="CON-2026-0001",
    contract_status=ContractStatus.SIGNED, total_cents=500_000, paid_cents=200_000,
    refunded_cents=0, balance_cents=300_000, balance_due_date=date(2026, 12, 12), overdue=False,
    payments=[AccountPaymentInfo(uuid4(), "PAG-2026-0001", PaymentKind.ADVANCE, 200_000,
                                 PaymentMethod.CASH, date(2026, 11, 22), False)],
)  # fmt: skip

STAFF = [StaffAssignment(uuid4(), "Pedro Quispe", "Mozo", WorkerFunction.WAITER, None, NOW, NOW)]


@dataclass
class Calls:
    accounts: list[UUID] = field(default_factory=list)
    staff: list[UUID] = field(default_factory=list)


@dataclass
class SheetFakes:
    staff: list[StaffAssignment] = field(default_factory=list)
    calls: Calls = field(default_factory=Calls)

    async def details(self, event_id: UUID) -> EventDetail | None:
        return DETAIL if event_id == EVENT_ID else None

    async def follow_up(self, event_id: UUID) -> EventFollowUp:
        return FOLLOW_UP

    async def materials(self, event_id: UUID) -> list[EventMaterialInfo]:
        return MATERIALS

    async def accounts(self, event_id: UUID) -> EventAccount | None:
        self.calls.accounts.append(event_id)
        return ACCOUNT

    async def event_staff(self, event_id: UUID) -> list[StaffAssignment]:
        self.calls.staff.append(event_id)
        return self.staff

    async def user_names(self, user_ids: Iterable[UUID]) -> dict[UUID, str]:
        known = {COORDINATOR: "Rosa Huamán", AUTHOR: "Harold Canaza"}
        return {i: known[i] for i in user_ids if i in known}
