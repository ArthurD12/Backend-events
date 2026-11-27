"""Registro de consultas del asistente con PostgreSQL real (sin llamar al proveedor).

Necesita Docker: `uv run pytest -m integration`.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.assistant.application.ports.query_log import QueryFilter
from local_eventos.modules.assistant.domain.feedback import Feedback, FeedbackValue
from local_eventos.modules.assistant.domain.query_record import QueryRecord, QueryStatus, ToolUse
from local_eventos.modules.assistant.infrastructure.feedback_log import SqlAlchemyFeedbackLog
from local_eventos.modules.assistant.infrastructure.query_log import SqlAlchemyQueryLog
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 11, 26, 15, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("DATABASE_URL", url)
            command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        yield url


@pytest.fixture
async def engine(database_url: str) -> AsyncEngine:
    engine = create_engine(database_url)
    yield engine  # type: ignore[misc]
    await engine.dispose()


def record(user_id, at: datetime, status: QueryStatus = QueryStatus.OK) -> QueryRecord:  # type: ignore[no-untyped-def]
    return QueryRecord(
        uuid4(), user_id, at, "¿saldo?", (ToolUse("event_account", {"code": "EV-1"}),),
        "S/ 10.00", 10, 5, 120, status,
    )  # fmt: skip


async def test_add_count_and_search(engine: AsyncEngine) -> None:
    user, other = uuid4(), uuid4()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        log = SqlAlchemyQueryLog(session)
        await log.add(record(user, NOW - timedelta(minutes=90)))
        await log.add(record(user, NOW - timedelta(minutes=10), QueryStatus.REFUSED))
        await log.add(record(other, NOW))
    async with sessions() as session:
        log = SqlAlchemyQueryLog(session)
        assert await log.count_since(user, NOW - timedelta(hours=1)) == 1
        found, total = await log.search(QueryFilter(user_id=user), limit=10, offset=0)
        assert total == 2 and [r.status for r in found] == [QueryStatus.REFUSED, QueryStatus.OK]
        assert found[0].tools == (ToolUse("event_account", {"code": "EV-1"}),)
        _, since_total = await log.search(
            QueryFilter(since=NOW - timedelta(minutes=30)), limit=10, offset=0
        )
        assert since_total == 2


async def test_table_is_append_only(engine: AsyncEngine) -> None:
    user = uuid4()
    async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
        await SqlAlchemyQueryLog(session).add(record(user, NOW))
    for sql in ("UPDATE assistant_queries SET answer = 'x'", "DELETE FROM assistant_queries"):
        with pytest.raises(DBAPIError, match="no se puede modificar"):
            async with engine.begin() as conn:
                await conn.execute(text(sql))


async def test_get_returns_the_query_or_none(engine: AsyncEngine) -> None:
    user = uuid4()
    saved = record(user, NOW)
    async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
        await SqlAlchemyQueryLog(session).add(saved)
    async with async_sessionmaker(engine)() as session:
        log = SqlAlchemyQueryLog(session)
        found = await log.get(saved.id)
        assert found is not None and found.user_id == user and found.question == "¿saldo?"
        assert await log.get(uuid4()) is None


async def test_feedback_latest_wins_and_table_is_append_only(engine: AsyncEngine) -> None:
    user, other = uuid4(), uuid4()
    graded, plain, regraded = record(user, NOW), record(user, NOW), record(other, NOW)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        queries, feedback = SqlAlchemyQueryLog(session), SqlAlchemyFeedbackLog(session)
        for query in (graded, plain, regraded):
            await queries.add(query)
        # mismo instante: la última se decide por el orden de inserción, no por la fecha
        await feedback.add(Feedback(graded.id, user, FeedbackValue.INCORRECT, "mal", NOW))
        await feedback.add(Feedback(graded.id, user, FeedbackValue.CORRECT, None, NOW))
        await feedback.add(Feedback(regraded.id, other, FeedbackValue.INCORRECT, None, NOW))
    async with sessions() as session:
        latest = await SqlAlchemyFeedbackLog(session).latest([graded.id, plain.id, regraded.id])
        assert set(latest) == {graded.id, regraded.id}
        assert (
            latest[graded.id].value is FeedbackValue.CORRECT and latest[graded.id].comment is None
        )
        assert await SqlAlchemyFeedbackLog(session).latest([]) == {}
    for sql in (
        "UPDATE assistant_feedback SET value = 'correct'",
        "DELETE FROM assistant_feedback",
    ):
        with pytest.raises(DBAPIError, match="no se pueden modificar"):
            async with engine.begin() as conn:
                await conn.execute(text(sql))
