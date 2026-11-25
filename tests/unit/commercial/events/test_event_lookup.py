"""`commercial.public_api.event_lookup`: lo que otros módulos saben de un evento (017, T-01)."""

from datetime import UTC, date, datetime, time
from uuid import uuid4

from local_eventos.modules.commercial.application.events.use_cases.event_lookup import LookupEvent
from local_eventos.modules.commercial.domain.events.event import Event, EventStatus
from local_eventos.modules.commercial.domain.quotes.quote import EventType
from local_eventos.modules.commercial.public_api import EventInfo, EventLookup

from .fakes import InMemoryEventRepository


def _event() -> Event:
    return Event(
        id=uuid4(),
        code="EVT-2026-0007",
        contract_id=uuid4(),
        quote_id=uuid4(),
        client_id=uuid4(),
        event_type=EventType.WEDDING,
        event_date=date(2026, 12, 19),
        start_time=time(20),
        end_time=time(3),
        venue="Local Los Jardines",
        guests=120,
        coordinator_id=uuid4(),
        status=EventStatus.CONFIRMED,
        services=(),
        created_by=uuid4(),
        created_at=datetime(2026, 11, 22, 15, tzinfo=UTC),
    )


async def test_devuelve_codigo_estado_fecha_y_horario() -> None:
    events = InMemoryEventRepository()
    event = _event()
    await events.add(event)
    lookup: EventLookup = LookupEvent(events)

    found = await lookup(event.id)

    assert found == EventInfo(
        id=event.id,
        code="EVT-2026-0007",
        status=EventStatus.CONFIRMED,
        event_date=date(2026, 12, 19),
        start_time=time(20),
        end_time=time(3),
    )


async def test_evento_inexistente_devuelve_none() -> None:
    assert await LookupEvent(InMemoryEventRepository())(uuid4()) is None
