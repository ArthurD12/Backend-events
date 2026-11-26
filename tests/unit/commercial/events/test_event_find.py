"""`commercial.public_api.events_find`: eventos por fecha, cliente, tipo y estado (024, T-02)."""

from dataclasses import replace
from datetime import UTC, date, datetime, time
from uuid import uuid4

from local_eventos.modules.commercial.application.events.use_cases.event_search import FindEvents
from local_eventos.modules.commercial.domain.events.event import Event, EventStatus
from local_eventos.modules.commercial.domain.quotes.quote import EventType
from local_eventos.modules.commercial.public_api import EventFindLookup

from .fakes import InMemoryEventRepository

ANA, LUIS = uuid4(), uuid4()


def _event(code: str, client_id, day: int, status: EventStatus, kind: EventType) -> Event:  # type: ignore[no-untyped-def]
    return Event(
        id=uuid4(), code=code, contract_id=uuid4(), quote_id=uuid4(), client_id=client_id,
        event_type=kind, event_date=date(2026, 12, day), start_time=time(20), end_time=time(3),
        venue="Local", guests=50, coordinator_id=uuid4(), status=status, services=(),
        created_by=uuid4(), created_at=datetime(2026, 11, 22, 15, tzinfo=UTC),
    )  # fmt: skip


async def _lookup() -> EventFindLookup:
    repo = InMemoryEventRepository({ANA: "Ana Torres", LUIS: "Luis Ramos"})
    for event in (
        _event("EV-1", ANA, 5, EventStatus.CONFIRMED, EventType.WEDDING),
        _event("EV-2", LUIS, 12, EventStatus.SCHEDULED, EventType.BIRTHDAY),
        _event("EV-3", ANA, 20, EventStatus.CANCELLED, EventType.WEDDING),
    ):
        await repo.add(replace(event))
    return FindEvents(repo)


async def test_filters_by_dates_client_type_and_status() -> None:
    find = await _lookup()
    assert [e.code for e in (await find(date_from=date(2026, 12, 10))).items] == ["EV-2", "EV-3"]
    assert [e.code for e in (await find(text="torres")).items] == ["EV-1", "EV-3"]
    assert [e.code for e in (await find(event_type=EventType.BIRTHDAY)).items] == ["EV-2"]
    assert [e.code for e in (await find(status=EventStatus.CANCELLED)).items] == ["EV-3"]
    both = await find(text="Ana", status=EventStatus.CONFIRMED, date_to=date(2026, 12, 6))
    assert [e.code for e in both.items] == ["EV-1"]


async def test_limit_cuts_items_but_not_the_total() -> None:
    result = await (await _lookup())(limit=1)
    assert len(result.items) == 1 and result.total == 3
