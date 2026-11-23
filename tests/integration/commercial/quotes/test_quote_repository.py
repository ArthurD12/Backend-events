"""Repositorio de cotizaciones contra PostgreSQL real (HU07–HU08). Necesita Docker.

Las tablas y los triggers se crean con las migraciones, igual que en producción.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteFilters,
)
from local_eventos.modules.commercial.domain.clients.client import Client, DocumentType
from local_eventos.modules.commercial.domain.quotes.quote import (
    EventDetails,
    EventType,
    LineKind,
    LineUnit,
    Quote,
    QuoteLine,
    QuoteStatus,
)
from local_eventos.modules.commercial.infrastructure.client_repository import (
    SqlAlchemyClientRepository,
)
from local_eventos.modules.commercial.infrastructure.quote_repository import (
    SqlAlchemyQuoteRepository,
)
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[4]
TODAY = date(2026, 11, 22)
NOW = datetime(2026, 11, 22, 15, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("DATABASE_URL", url)
            command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        yield url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url)
    yield engine
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE commercial_event_services, commercial_events, commercial_event_counters,"
                " commercial_contracts, commercial_contract_counters,"
                " commercial_quote_lines, commercial_quotes, commercial_quote_counters,"
                " commercial_client_document_corrections, commercial_clients"
            )
        )
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _client(sessions: async_sessionmaker[AsyncSession], name: str, number: str) -> Client:
    client = Client.register(
        name=name, document_type=DocumentType.DNI, document_number=number, phone="987654321"
    )
    async with sessions.begin() as session:
        await SqlAlchemyClientRepository(session).add(client)
    return client


def _quote(client: Client, code: str, **changes: object) -> Quote:
    data: dict[str, object] = {
        "code": code,
        "client_id": client.id,
        "details": EventDetails(
            event_type=EventType.WEDDING,
            event_date=date(2026, 12, 19),
            start_time=time(20),
            end_time=time(3),
            venue="Local Los Jardines",
            guests=100,
        ),
        "lines": [
            QuoteLine(
                kind=LineKind.SERVICE,
                description="Buffet criollo",
                unit=LineUnit.PER_PERSON,
                quantity=100,
                unit_price_cents=4500,
                service_id=uuid4(),
                catalog_price_cents=4500,
            ),
            QuoteLine(
                kind=LineKind.EXTRA,
                description="Movilidad",
                unit=LineUnit.PER_UNIT,
                quantity=1,
                unit_price_cents=15000,
            ),
        ],
        "created_by": uuid4(),
        "now": NOW,
        "today": TODAY,
        **changes,
    }
    return Quote.create(**data)  # type: ignore[arg-type]


async def _save(sessions: async_sessionmaker[AsyncSession], quote: Quote) -> Quote:
    async with sessions.begin() as session:
        await SqlAlchemyQuoteRepository(session).add(quote)
    return quote


async def test_ca07_guarda_y_lee_la_cotizacion_con_sus_lineas(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    client = await _client(sessions, "Familia Quispe", "40000001")
    quote = await _save(sessions, _quote(client, "COT-2026-0001", notes="Prefieren mesas redondas"))

    async with sessions() as session:
        saved = await SqlAlchemyQuoteRepository(session).get(quote.id)
        total = await session.scalar(
            text("SELECT total_cents FROM commercial_quotes WHERE id = :id"), {"id": quote.id}
        )

    assert saved == quote
    assert total == 465_000


async def test_ca08_1_editar_reemplaza_las_lineas_y_el_total(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    client = await _client(sessions, "Familia Quispe", "40000001")
    quote = await _save(sessions, _quote(client, "COT-2026-0001"))
    quote.update(
        details=quote.details,
        lines=[quote.lines[1]],
        valid_until=TODAY + timedelta(days=30),
        today=TODAY,
    )
    async with sessions.begin() as session:
        await SqlAlchemyQuoteRepository(session).update(quote)

    async with sessions() as session:
        saved = await SqlAlchemyQuoteRepository(session).get(quote.id)
    assert saved is not None
    assert [line.description for line in saved.lines] == ["Movilidad"]
    assert saved.total_cents == 15_000


async def test_ca08_2_cambiar_estado_no_toca_las_lineas(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    client = await _client(sessions, "Familia Quispe", "40000001")
    quote = await _save(sessions, _quote(client, "COT-2026-0001"))

    for status in (QuoteStatus.SENT, QuoteStatus.DRAFT, QuoteStatus.SENT, QuoteStatus.ACCEPTED):
        quote.change_status(status, TODAY)
        async with sessions.begin() as session:
            await SqlAlchemyQuoteRepository(session).update(quote)

    async with sessions() as session:
        saved = await SqlAlchemyQuoteRepository(session).get(quote.id)
    assert saved is not None and saved.status is QuoteStatus.ACCEPTED
    assert len(saved.lines) == 2


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE commercial_quotes SET guests = 999",
        "UPDATE commercial_quote_lines SET quantity = 999",
        "DELETE FROM commercial_quote_lines",
    ],
)
async def test_ca08_4_la_base_bloquea_editar_una_cotizacion_aceptada(
    sessions: async_sessionmaker[AsyncSession], statement: str
) -> None:
    client = await _client(sessions, "Familia Quispe", "40000001")
    quote = await _save(sessions, _quote(client, "COT-2026-0001"))
    quote.change_status(QuoteStatus.ACCEPTED, TODAY)
    async with sessions.begin() as session:
        await SqlAlchemyQuoteRepository(session).update(quote)

    with pytest.raises(DBAPIError, match="borrador"):
        async with sessions.begin() as session:
            await session.execute(text(statement))


async def test_ca07_4_dos_cotizaciones_simultaneas_no_repiten_codigo(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async def take() -> int:
        async with sessions.begin() as session:
            return await SqlAlchemyQuoteRepository(session).next_number(2026)

    numbers = await asyncio.gather(*(take() for _ in range(10)))

    assert sorted(numbers) == list(range(1, 11))
    async with sessions.begin() as session:
        assert await SqlAlchemyQuoteRepository(session).next_number(2027) == 1


async def test_ca08_5_busca_por_codigo_cliente_sin_tildes_estado_y_fecha(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    jose = await _client(sessions, "José Ramírez", "40000001")
    colegio = await _client(sessions, "Colegio San Martín", "40000002")
    first = await _save(
        sessions, _quote(jose, "COT-2026-0001", valid_until=TODAY + timedelta(days=2))
    )
    second = await _save(sessions, _quote(colegio, "COT-2026-0002"))
    second.change_status(QuoteStatus.SENT, TODAY)
    async with sessions.begin() as session:
        await SqlAlchemyQuoteRepository(session).update(second)
    later = TODAY + timedelta(days=5)  # la primera ya venció

    async with sessions() as session:
        search = SqlAlchemyQuoteRepository(session).search

        async def codes(filters: QuoteFilters) -> list[str]:
            items, _ = await search(filters, today=later, limit=50, offset=0)
            return [item.code for item in items]

        assert await codes(QuoteFilters(text="jose ramirez")) == ["COT-2026-0001"]
        assert await codes(QuoteFilters(text="0002")) == ["COT-2026-0002"]
        assert await codes(QuoteFilters(text="%")) == []
        assert await codes(QuoteFilters(status=QuoteStatus.EXPIRED)) == ["COT-2026-0001"]
        assert await codes(QuoteFilters(status=QuoteStatus.DRAFT)) == []
        assert await codes(QuoteFilters(status=QuoteStatus.SENT)) == ["COT-2026-0002"]
        assert await codes(QuoteFilters(client_id=colegio.id)) == ["COT-2026-0002"]
        assert await codes(QuoteFilters(event_date_from=date(2026, 12, 20))) == []
        items, total = await search(QuoteFilters(), today=later, limit=1, offset=0)
    assert total == 2 and len(items) == 1
    assert items[0].client_name in ("José Ramírez", "Colegio San Martín")
    assert {first.id, second.id} >= {items[0].id}
