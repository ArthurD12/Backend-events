"""RateQuery y SearchQueries con valoración, sin base de datos (024, HU40)."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from local_eventos.modules.assistant.application.errors import QueryNotFoundError
from local_eventos.modules.assistant.application.ports.query_log import QueryFilter
from local_eventos.modules.assistant.application.use_cases.rate_query import RateQuery
from local_eventos.modules.assistant.application.use_cases.search_queries import SearchQueries
from local_eventos.modules.assistant.domain.feedback import FeedbackValue
from local_eventos.modules.assistant.domain.query_record import QueryRecord, QueryStatus
from tests.unit.assistant.fakes import FixedClock, InMemoryFeedbackLog, InMemoryQueryLog

AUTHOR = uuid4()


def _query(user: UUID = AUTHOR) -> QueryRecord:
    return QueryRecord(
        uuid4(), user, datetime(2026, 11, 26, 10, tzinfo=UTC), "q", (), "a", 1, 2, 3,
        QueryStatus.OK,
    )  # fmt: skip


async def test_author_rates_and_the_comment_is_cleaned() -> None:
    log, feedback = InMemoryQueryLog(), InMemoryFeedbackLog()
    query = _query()
    await log.add(query)
    saved = await RateQuery(log, feedback, FixedClock())(
        AUTHOR, query.id, FeedbackValue.INCORRECT, "  mal   el total "
    )
    assert saved.comment == "mal el total" and saved.created_at == FixedClock().now()
    assert feedback.rows == [saved]


async def test_blank_comment_becomes_none_and_long_one_is_cut() -> None:
    log, feedback = InMemoryQueryLog(), InMemoryFeedbackLog()
    query = _query()
    await log.add(query)
    rate = RateQuery(log, feedback, FixedClock())
    assert (await rate(AUTHOR, query.id, FeedbackValue.CORRECT, "   ")).comment is None
    assert (
        len((await rate(AUTHOR, query.id, FeedbackValue.CORRECT, "x" * 500)).comment or "") == 300
    )


async def test_only_the_author_can_rate() -> None:
    log, feedback = InMemoryQueryLog(), InMemoryFeedbackLog()
    query = _query()
    await log.add(query)
    with pytest.raises(QueryNotFoundError):
        await RateQuery(log, feedback, FixedClock())(uuid4(), query.id, FeedbackValue.CORRECT)
    with pytest.raises(QueryNotFoundError):
        await RateQuery(log, feedback, FixedClock())(AUTHOR, uuid4(), FeedbackValue.CORRECT)
    assert feedback.rows == []


async def test_search_attaches_the_latest_feedback() -> None:
    log, feedback = InMemoryQueryLog(), InMemoryFeedbackLog()
    graded, plain = _query(), _query()
    await log.add(graded)
    await log.add(plain)
    rate = RateQuery(log, feedback, FixedClock())
    await rate(AUTHOR, graded.id, FeedbackValue.INCORRECT)
    await rate(AUTHOR, graded.id, FeedbackValue.CORRECT)
    page = await SearchQueries(log, feedback)(QueryFilter(user_id=AUTHOR))
    assert page.feedback[graded.id].value is FeedbackValue.CORRECT and plain.id not in page.feedback
