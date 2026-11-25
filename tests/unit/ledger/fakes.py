"""Pagos y movimientos en memoria para probar sin base de datos."""

from datetime import UTC, date, datetime
from uuid import UUID

from local_eventos.modules.ledger.application.errors import (
    MovementAlreadyVoidedError,
    PaymentAlreadyVoidedError,
)
from local_eventos.modules.ledger.application.ports.movement_repository import (
    MonthlyMovementTotal,
    MovementEntry,
    MovementFilters,
    MovementState,
)
from local_eventos.modules.ledger.application.ports.payment_repository import (
    MonthlyPaymentTotal,
    PaymentEntry,
)
from local_eventos.modules.ledger.domain.movement import (
    CashMovement,
    MovementCategory,
    MovementVoid,
)
from local_eventos.modules.ledger.domain.payment import Payment, PaymentKind, PaymentVoid


class FakeLedgerClock:
    def __init__(
        self,
        today: date = date(2026, 11, 22),
        now: datetime = datetime(2026, 11, 22, 15, tzinfo=UTC),
    ) -> None:
        self._today, self._now = today, now

    def now(self) -> datetime:
        return self._now

    def today(self) -> date:
        return self._today


class InMemoryPaymentRepository:
    def __init__(self) -> None:
        self.payments: list[Payment] = []
        self.voids: dict[UUID, PaymentVoid] = {}
        self.counters: dict[int, int] = {}

    async def add(self, payment: Payment) -> None:
        self.payments.append(payment)

    async def next_number(self, year: int) -> int:
        self.counters[year] = self.counters.get(year, 0) + 1
        return self.counters[year]

    async def get(self, payment_id: UUID) -> PaymentEntry | None:
        found = next((p for p in self.payments if p.id == payment_id), None)
        return PaymentEntry(found, self.voids.get(found.id)) if found else None

    async def list_for_contract(self, contract_id: UUID) -> list[Payment]:
        return [p for p in self.payments if p.contract_id == contract_id]

    async def entries_for_contract(self, contract_id: UUID) -> list[PaymentEntry]:
        return [PaymentEntry(p, self.voids.get(p.id)) for p in self.payments
                if p.contract_id == contract_id]  # fmt: skip

    async def add_void(self, void: PaymentVoid) -> None:
        if void.payment_id in self.voids:
            raise PaymentAlreadyVoidedError()
        self.voids[void.payment_id] = void

    async def monthly_totals(self, date_from: date, date_to: date) -> list[MonthlyPaymentTotal]:
        totals: dict[tuple[int, int, PaymentKind], int] = {}
        for p in self.payments:
            if p.id in self.voids or not date_from <= p.paid_on <= date_to:
                continue
            key = (p.paid_on.year, p.paid_on.month, p.kind)
            totals[key] = totals.get(key, 0) + p.amount_cents
        return [
            MonthlyPaymentTotal(year=y, month=m, kind=k, amount_cents=v)
            for (y, m, k), v in totals.items()
        ]


class InMemoryMovementRepository:
    def __init__(self) -> None:
        self.movements: list[CashMovement] = []
        self.voids: dict[UUID, MovementVoid] = {}

    async def add(self, movement: CashMovement) -> None:
        self.movements.append(movement)

    async def get(self, movement_id: UUID) -> MovementEntry | None:
        found = next((m for m in self.movements if m.id == movement_id), None)
        return MovementEntry(found, self.voids.get(found.id)) if found else None

    async def add_void(self, void: MovementVoid) -> None:
        if void.movement_id in self.voids:
            raise MovementAlreadyVoidedError()
        self.voids[void.movement_id] = void

    async def search(
        self, filters: MovementFilters, *, limit: int, offset: int
    ) -> tuple[list[MovementEntry], int]:
        found = [
            MovementEntry(m, self.voids.get(m.id))
            for m in sorted(
                self.movements, key=lambda m: (m.occurred_on, m.recorded_at), reverse=True
            )  # fmt: skip
            if (filters.date_from is None or m.occurred_on >= filters.date_from)
            and (filters.date_to is None or m.occurred_on <= filters.date_to)
            and (filters.type is None or m.type is filters.type)
            and (filters.category is None or m.category is filters.category)
            and (filters.event_id is None or m.event_id == filters.event_id)
            and (
                filters.state is None
                or (filters.state is MovementState.VOIDED) == (m.id in self.voids)
            )
        ]
        return found[offset : offset + limit], len(found)

    async def monthly_totals(self, date_from: date, date_to: date) -> list[MonthlyMovementTotal]:
        totals: dict[tuple[int, int, MovementCategory], int] = {}
        for m in self.movements:
            if m.id in self.voids or not date_from <= m.occurred_on <= date_to:
                continue
            key = (m.occurred_on.year, m.occurred_on.month, m.category)
            totals[key] = totals.get(key, 0) + m.amount_cents
        return [
            MonthlyMovementTotal(year=y, month=mo, category=c, amount_cents=v)
            for (y, mo, c), v in totals.items()
        ]

    async def event_totals(self, event_id: UUID) -> dict[MovementCategory, int]:
        totals: dict[MovementCategory, int] = {}
        for m in self.movements:
            if m.id not in self.voids and m.event_id == event_id:
                totals[m.category] = totals.get(m.category, 0) + m.amount_cents
        return totals
