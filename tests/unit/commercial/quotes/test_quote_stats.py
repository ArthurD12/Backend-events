"""Números de cotizaciones para el panel del administrador (HU31, CA-31.1 a CA-31.4, CA-31.6)."""

from datetime import date, timedelta
from uuid import uuid4

from local_eventos.modules.commercial.application.quotes.use_cases.query_quotes import (
    ChangeQuoteStatus,
)
from local_eventos.modules.commercial.application.quotes.use_cases.quote_stats import GetQuoteStats
from local_eventos.modules.commercial.domain.quotes.quote import QuoteStatus

from .world import World


async def _quote(world: World, *, event_in_days: int = 30, **changes: object):  # type: ignore[no-untyped-def]
    event_date = world.clock.today() + timedelta(days=event_in_days)
    return await world.create()(world.command(event_date=event_date, **changes), created_by=uuid4())


async def test_ca31_1_cuenta_borradores_y_enviadas_vigentes(world: World) -> None:
    await _quote(world)
    sent = await _quote(world)
    expired = await _quote(world, valid_until=world.clock.today() + timedelta(days=1))
    change = ChangeQuoteStatus(world.quotes, world.clock)
    await change(sent.id, QuoteStatus.SENT)
    await change(expired.id, QuoteStatus.SENT)
    world.clock.advance(days=3)  # la tercera vence

    stats = await GetQuoteStats(world.quotes, world.clock)()

    assert (stats.drafts, stats.sent_pending) == (1, 1)


async def test_ca31_2_y_ca31_6_creadas_aceptadas_y_monto_del_mes(world: World) -> None:
    accepted = await _quote(world)
    await _quote(world)
    await ChangeQuoteStatus(world.quotes, world.clock)(accepted.id, QuoteStatus.ACCEPTED)
    world.clock.advance(days=40)  # diciembre → otra cotización en el mes siguiente
    await _quote(world)

    november = await GetQuoteStats(world.quotes, world.clock)(2026, 11)
    january = await GetQuoteStats(world.quotes, world.clock)(2027, 1)
    current = await GetQuoteStats(world.quotes, world.clock)()

    assert (november.created_in_month, november.accepted_in_month) == (2, 1)
    assert november.accepted_amount_cents == accepted.total_cents
    assert (january.created_in_month, january.accepted_amount_cents) == (1, 0)
    assert (current.year, current.month) == (2027, 1)


async def test_ca31_3_proximas_fechas_aceptadas_en_30_dias_ordenadas(world: World) -> None:
    far = await _quote(world, event_in_days=45)
    later = await _quote(world, event_in_days=20)
    soon = await _quote(world, event_in_days=5)
    pending = await _quote(world, event_in_days=3)
    change = ChangeQuoteStatus(world.quotes, world.clock)
    for quote in (far, later, soon):
        await change(quote.id, QuoteStatus.ACCEPTED)

    stats = await GetQuoteStats(world.quotes, world.clock)()

    assert [q.id for q in stats.upcoming] == [soon.id, later.id]
    assert pending.id not in [q.id for q in stats.upcoming]


async def test_ca31_4_las_5_mas_recientes(world: World) -> None:
    for _ in range(7):
        await _quote(world)
        world.clock.advance(minutes=1)

    stats = await GetQuoteStats(world.quotes, world.clock)()

    assert [q.code for q in stats.recent] == [f"COT-2026-000{n}" for n in (7, 6, 5, 4, 3)]


async def test_sin_cotizaciones_todo_en_cero(world: World) -> None:
    stats = await GetQuoteStats(world.quotes, world.clock)()

    assert (stats.drafts, stats.created_in_month, stats.accepted_amount_cents) == (0, 0, 0)
    assert stats.upcoming == stats.recent == []
    assert stats.month == date(2026, 11, 1).month
