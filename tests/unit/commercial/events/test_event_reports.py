"""Consultas de commercial para reportes y panel (HU31–HU34), con piezas en memoria."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

from local_eventos.modules.commercial.application.events.use_cases.event_reports import (
    EventReportFilters,
    GetReceivables,
    ListEventReport,
    ListUpcomingEvents,
    LookupEventRefs,
    Receivables,
)
from local_eventos.modules.commercial.domain.contracts.contract import Contract, ContractStatus
from local_eventos.modules.commercial.domain.events.event import Event, EventStatus
from local_eventos.modules.commercial.domain.quotes.quote import EventType
from local_eventos.modules.ledger.public_api import ContractPaidTotals

from ..contracts.fakes import InMemoryContractRepository
from .fakes import InMemoryEventRepository

TODAY = date(2026, 11, 25)
NOW = datetime(2026, 11, 25, 15, tzinfo=UTC)
CLIENT = uuid4()


class FakeClock:
    def now(self) -> datetime:
        return NOW

    def today(self) -> date:
        return TODAY


class FakePaidTotals:
    def __init__(self) -> None:
        self.totals: dict[UUID, ContractPaidTotals] = {}
        self.calls = 0

    async def __call__(self, contract_ids: list[UUID]) -> dict[UUID, ContractPaidTotals]:
        self.calls += 1
        return {c: self.totals.get(c, ContractPaidTotals()) for c in contract_ids}


class World:
    def __init__(self) -> None:
        self.events = InMemoryEventRepository({CLIENT: "José Ramírez"})
        self.contracts = InMemoryContractRepository()
        self.paid = FakePaidTotals()

    async def contract(
        self, *, total: int = 100_000, status: ContractStatus = ContractStatus.SIGNED,
        event_date: date = TODAY + timedelta(days=20), paid: int = 0, refunded: int = 0,
    ) -> Contract:  # fmt: skip
        contract = Contract(
            id=uuid4(), code=f"CON-2026-{len(self.contracts.contracts) + 1:04d}",
            quote_id=uuid4(), client_id=CLIENT, event_date=event_date, total_cents=total,
            advance_cents=total // 2, balance_due_date=event_date - timedelta(days=7),
            status=status, created_by=uuid4(), created_at=NOW,
        )  # fmt: skip
        await self.contracts.add(contract)
        self.paid.totals[contract.id] = ContractPaidTotals(paid, refunded)
        return contract

    async def event(self, contract: Contract, status: EventStatus = EventStatus.SCHEDULED) -> Event:
        event = Event(
            id=uuid4(), code=f"EVT-2026-{len(self.events.events) + 1:04d}",
            contract_id=contract.id, quote_id=contract.quote_id, client_id=CLIENT,
            event_type=EventType.WEDDING, event_date=contract.event_date, start_time=time(20),
            end_time=time(23), venue="Local", guests=100, coordinator_id=uuid4(), status=status,
            services=(), created_by=uuid4(), created_at=NOW,
        )  # fmt: skip
        await self.events.add(event)
        return event

    def report(self) -> ListEventReport:
        return ListEventReport(self.events, self.contracts, self.paid, FakeClock())


async def test_ca32_1_total_pagado_neto_saldo_y_vencido() -> None:
    world = World()
    late = await world.contract(event_date=TODAY + timedelta(days=3), paid=60_000, refunded=0)
    ok = await world.contract(paid=50_000, refunded=10_000)
    await world.event(late)
    await world.event(ok)

    items = await world.report()(EventReportFilters())

    assert [(i.code, i.paid_cents, i.balance_cents, i.overdue) for i in items] == [
        ("EVT-2026-0001", 60_000, 40_000, True),
        ("EVT-2026-0002", 40_000, 60_000, False),
    ]
    assert items[0].client_name == "José Ramírez"
    assert world.paid.calls == 1  # una sola consulta de pagos para todos los eventos


async def test_ca32_1_filtra_por_rango_y_estado() -> None:
    world = World()
    await world.event(await world.contract(event_date=TODAY + timedelta(days=5)))
    await world.event(
        await world.contract(event_date=TODAY + timedelta(days=50)), EventStatus.CONFIRMED
    )

    by_range = await world.report()(
        EventReportFilters(date_from=TODAY, date_to=TODAY + timedelta(days=10))
    )
    by_status = await world.report()(EventReportFilters(status=EventStatus.CONFIRMED))

    assert [i.code for i in by_range] == ["EVT-2026-0001"]
    assert [i.code for i in by_status] == ["EVT-2026-0002"]


async def test_ca31_7_proximos_14_dias_sin_cancelados() -> None:
    world = World()
    await world.event(await world.contract(event_date=TODAY + timedelta(days=2)))
    await world.event(
        await world.contract(event_date=TODAY + timedelta(days=3)), EventStatus.CANCELLED
    )
    await world.event(await world.contract(event_date=TODAY + timedelta(days=30)))

    items = await ListUpcomingEvents(world.report(), FakeClock())()

    assert [i.code for i in items] == ["EVT-2026-0001"]


async def test_ca31_9_cobros_pendientes_de_contratos_firmados() -> None:
    world = World()
    await world.contract(event_date=TODAY + timedelta(days=3), paid=50_000)  # vencido
    await world.contract(paid=70_000)
    await world.contract(paid=100_000)  # pagado completo
    await world.contract(status=ContractStatus.PENDING_SIGNATURE)  # no cuenta

    found = await GetReceivables(world.contracts, world.paid, FakeClock())()

    assert found == Receivables(
        total_cents=80_000, contracts=2, overdue_contracts=1, overdue_cents=50_000
    )


async def test_refs_por_evento_y_por_contrato() -> None:
    world = World()
    with_event = await world.contract()
    event = await world.event(with_event)
    without_event = await world.contract()

    refs = await LookupEventRefs(world.events, world.contracts)(
        [event.id, uuid4()], [with_event.id, without_event.id]
    )

    assert refs.by_event == {event.id: "EVT-2026-0001"}
    assert refs.by_contract == {with_event.id: "EVT-2026-0001", without_event.id: "CON-2026-0002"}
