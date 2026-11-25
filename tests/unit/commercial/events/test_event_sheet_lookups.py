"""Consultas de `commercial.public_api` para la ficha del evento (019, T-01). Sin base de datos."""

from datetime import date, timedelta
from uuid import UUID, uuid4

from local_eventos.modules.commercial.application.events.use_cases.event_sheet import (
    GetEventAccount,
    GetEventDetail,
    GetEventFollowUp,
)
from local_eventos.modules.commercial.domain.clients.client import Client, DocumentType
from local_eventos.modules.commercial.domain.events.activity import (
    ActivityStatus,
    EventActivity,
    EventNote,
)
from local_eventos.modules.commercial.domain.events.event import Event
from local_eventos.modules.commercial.domain.quotes.quote import LineKind
from local_eventos.modules.commercial.public_api import (
    ContractStatus,
    EventAccountLookup,
    EventDetailLookup,
    EventFollowUpLookup,
)
from local_eventos.modules.ledger.domain.payment import (
    Payment,
    PaymentKind,
    PaymentMethod,
    PaymentVoid,
)
from local_eventos.modules.ledger.public_api import PaymentEntry
from tests.unit.commercial.clients.fakes import InMemoryClientRepository
from tests.unit.commercial.contracts.fakes import InMemoryContractRepository
from tests.unit.commercial.quotes.fakes import FakeClock

from .fakes import InMemoryEventLogRepository, InMemoryEventRepository
from .test_event import NOW, TODAY, _accepted_quote, _contract

ADVANCE = 200_000


def _payment(contract_id: UUID, kind: PaymentKind, amount: int, number: str) -> Payment:
    return Payment.record(
        number=number, contract_id=contract_id, kind=kind, amount_cents=amount,
        method=PaymentMethod.CASH, reference=None, paid_on=TODAY, recorded_by=uuid4(),
        now=NOW, today=TODAY,
    )  # fmt: skip


async def _event_with_client() -> tuple[Event, InMemoryEventRepository, InMemoryClientRepository,
                                       InMemoryContractRepository]:  # fmt: skip
    client = Client.register(
        name="José Ramírez", document_type=DocumentType.DNI, document_number="40000001",
        phone="987654321",
    )  # fmt: skip
    clients = InMemoryClientRepository()
    await clients.add(client)
    quote = _accepted_quote()
    quote.client_id = client.id
    contract = _contract(quote)
    contracts = InMemoryContractRepository()
    await contracts.add(contract)
    event = Event.from_contract(
        code="EVT-2026-0001", contract=contract, quote=quote, coordinator_id=uuid4(),
        created_by=uuid4(), now=NOW,
    )  # fmt: skip
    events = InMemoryEventRepository()
    await events.add(event)
    return event, events, clients, contracts


async def test_detalle_con_cliente_y_servicios_sin_precios() -> None:
    event, events, clients, _ = await _event_with_client()
    lookup: EventDetailLookup = GetEventDetail(events, clients)

    detail = await lookup(event.id)

    assert detail is not None
    assert (detail.code, detail.guests, detail.ends_next_day) == ("EVT-2026-0001", 120, True)
    assert (detail.client.name, detail.client.document_number, detail.client.phone) == (
        "José Ramírez",
        "40000001",
        "987654321",
    )
    assert [(s.kind, s.description, s.quantity) for s in detail.services] == [
        (LineKind.SERVICE, "Buffet criollo", 120),
        (LineKind.EXTRA, "Movilidad", 1),
    ]
    assert not hasattr(detail.services[0], "unit_price_cents")
    assert await lookup(uuid4()) is None


async def test_seguimiento_con_actividades_y_ultimas_observaciones() -> None:
    log = InMemoryEventLogRepository()
    event_id, user = uuid4(), uuid4()
    first = EventActivity.create(
        event_id=event_id, description="Probar menú", responsible_id=user, created_by=user,
        now=NOW,
    )  # fmt: skip
    first.complete(by=user, now=NOW + timedelta(hours=1))
    second = EventActivity.create(
        event_id=event_id, description="Confirmar mozos", responsible_id=user, created_by=user,
        now=NOW + timedelta(minutes=5),
    )  # fmt: skip
    for activity in (first, second):
        await log.add_activity(activity)
    for i in range(7):
        await log.add_note(
            EventNote.create(
                event_id=event_id, text=f"Nota {i}", created_by=user, now=NOW + timedelta(minutes=i)
            )  # fmt: skip
        )
    lookup: EventFollowUpLookup = GetEventFollowUp(log)

    follow_up = await lookup(event_id)

    assert [(a.description, a.status) for a in follow_up.activities] == [
        ("Probar menú", ActivityStatus.DONE),
        ("Confirmar mozos", ActivityStatus.PENDING),
    ]
    assert [n.text for n in follow_up.recent_notes] == [f"Nota {i}" for i in (6, 5, 4, 3, 2)]


async def test_cuenta_del_contrato_con_pagos_y_anulados() -> None:
    event, events, _, contracts = await _event_with_client()
    contract_id = event.contract_id
    advance = _payment(contract_id, PaymentKind.ADVANCE, ADVANCE, "PAG-2026-0001")
    voided = _payment(contract_id, PaymentKind.INSTALLMENT, 50_000, "PAG-2026-0002")
    entries = [
        PaymentEntry(advance),
        PaymentEntry(voided, PaymentVoid(voided.id, "Error", uuid4(), NOW)),
    ]

    async def _entries(cid: UUID) -> list[PaymentEntry]:
        return entries if cid == contract_id else []

    lookup: EventAccountLookup = GetEventAccount(events, contracts, _entries, FakeClock())

    account = await lookup(event.id)

    assert account is not None
    assert account.contract_status is ContractStatus.SIGNED
    assert account.paid_cents == ADVANCE
    assert account.balance_cents == account.total_cents - ADVANCE
    assert account.balance_due_date < date(2026, 12, 19)
    assert [(p.number, p.voided) for p in account.payments] == [
        ("PAG-2026-0001", False),
        ("PAG-2026-0002", True),
    ]
    assert await lookup(uuid4()) is None
