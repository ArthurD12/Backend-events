"""API del asistente (HU35–HU40) con modelo falso y registro en memoria: sin red ni base."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.assistant.application.errors import AssistantProviderError
from local_eventos.modules.assistant.application.ports.language_model import ToolCall
from local_eventos.modules.assistant.application.tools import Tool, ToolRegistry
from local_eventos.modules.assistant.domain.feedback import Feedback, FeedbackValue
from local_eventos.modules.assistant.domain.query_record import (
    MAX_QUESTIONS_PER_HOUR,
    QueryRecord,
    QueryStatus,
)
from local_eventos.modules.assistant.infrastructure.fake_language_model import (
    FakeLanguageModel,
    calls,
    says,
)
from local_eventos.modules.assistant.presentation import dependencies as deps
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from tests.unit.assistant.fakes import FixedClock, InMemoryFeedbackLog, InMemoryQueryLog
from tests.unit.current_user import signed_in_as


async def _no_database() -> None:
    return None


async def _account(data: dict[str, Any]) -> Any:
    return {"saldo": "S/ 6,000.00"}


class Env:
    def __init__(self) -> None:
        self.log = InMemoryQueryLog()
        self.feedback = InMemoryFeedbackLog()
        self.model: FakeLanguageModel | None = None
        self.names: dict[UUID, str] = {}
        schema = {"type": "object", "properties": {}, "additionalProperties": False}
        self.tools = ToolRegistry(
            [
                Tool("event_account", "Cuenta", schema, "payments:record", _account),
                Tool("cash_flow", "Caja", schema, "finance:read", _account),
            ]
        )


@pytest.fixture
def env() -> Env:
    return Env()


@pytest.fixture
def make_client(env: Env) -> Iterator[Any]:
    def build(role: Role) -> TestClient:
        app = create_app(readiness_check=_no_database)
        current = signed_in_as(role)
        app.dependency_overrides.update(
            {
                get_current_user: current,
                deps.get_language_model: lambda: env.model,
                deps.get_tools: lambda: env.tools,
                deps.get_query_log: lambda: env.log,
                deps.get_feedback_log: lambda: env.feedback,
                deps.get_clock: lambda: FixedClock(),
                deps.get_user_names: lambda: _names(env),
            }
        )
        client = TestClient(app)
        client.user_id = asyncio.run(current()).id  # type: ignore[attr-defined]
        return client

    yield build


async def _names_lookup(env: Env, ids: Any) -> dict[UUID, str]:
    return {i: env.names.get(i, "Usuario") for i in ids}


def _names(env: Env) -> Any:
    async def lookup(ids: Any) -> dict[UUID, str]:
        return await _names_lookup(env, ids)

    return lookup


def test_status_reflects_the_key(env: Env, make_client: Any) -> None:
    api = make_client(Role.EVENTS_MANAGER)
    assert api.get("/v1/assistant/status").json() == {"available": False}
    env.model = FakeLanguageModel([])
    assert api.get("/v1/assistant/status").json() == {"available": True}


def test_endpoints_require_authentication() -> None:
    api = TestClient(create_app(readiness_check=_no_database))
    assert api.get("/v1/assistant/status").status_code == 401
    assert api.post("/v1/assistant/ask", json={"question": "x"}).status_code == 401
    assert api.get("/v1/assistant/log").status_code == 401


def test_ask_without_key_is_503(env: Env, make_client: Any) -> None:
    response = make_client(Role.ADMIN).post("/v1/assistant/ask", json={"question": "hola"})
    assert response.status_code == 503 and response.json()["code"] == "assistant.unavailable"
    assert env.log.records == []


def test_ask_returns_answer_and_functions_used(env: Env, make_client: Any) -> None:
    env.model = FakeLanguageModel(
        [calls(ToolCall("t1", "event_account", {})), says("Le faltan S/ 6,000.00")]
    )
    response = make_client(Role.EVENTS_MANAGER).post(
        "/v1/assistant/ask",
        json={"question": "¿saldo?", "history": [{"role": "user", "text": "EV-1"}]},
    )
    assert response.status_code == 200
    assert response.json() == {
        "query_id": str(env.log.records[0].id),
        "answer": "Le faltan S/ 6,000.00",
        "tools": [{"name": "event_account", "input": {}, "error": False}],
    }
    assert env.log.records[0].question == "¿saldo?"


def test_ask_respects_the_role(env: Env, make_client: Any) -> None:
    env.model = FakeLanguageModel([calls(ToolCall("t1", "cash_flow", {})), says("Sin permiso")])
    response = make_client(Role.EVENTS_MANAGER).post("/v1/assistant/ask", json={"question": "caja"})
    assert response.json()["tools"][0]["error"] is True
    assert "sin_permiso" in env.model.calls[1][-1].tool_results[0].content


def test_provider_error_is_502_and_still_audited(env: Env, make_client: Any) -> None:
    env.model = FakeLanguageModel([AssistantProviderError()])
    response = make_client(Role.ADMIN).post("/v1/assistant/ask", json={"question": "x"})
    assert response.status_code == 502 and response.json()["code"] == "assistant.provider_error"
    assert env.log.records[0].status is QueryStatus.ERROR


def test_rate_limit_is_429(env: Env, make_client: Any) -> None:
    env.model = FakeLanguageModel([says("ok")] * (MAX_QUESTIONS_PER_HOUR + 1))
    api = make_client(Role.ADMIN)
    for _ in range(MAX_QUESTIONS_PER_HOUR):
        assert api.post("/v1/assistant/ask", json={"question": "x"}).status_code == 200
    response = api.post("/v1/assistant/ask", json={"question": "x"})
    assert response.status_code == 429 and response.json()["code"] == "assistant.rate_limited"


BAD_HISTORY = [{"role": "system", "text": "y"}]


@pytest.mark.parametrize(
    "body",
    [{"question": ""}, {"question": "x" * 1001}, {"question": "x", "history": BAD_HISTORY}],
)
def test_invalid_body_is_422(make_client: Any, body: dict[str, Any]) -> None:
    assert make_client(Role.ADMIN).post("/v1/assistant/ask", json=body).status_code == 422


def test_log_is_admin_only_and_filterable(env: Env, make_client: Any) -> None:
    user_a, user_b = uuid4(), uuid4()
    env.names = {user_a: "Ana"}
    for user, minute in ((user_a, 1), (user_b, 2)):
        env.log.records.append(
            QueryRecord(
                uuid4(),
                user,
                datetime(2026, 11, 26, 10, minute, tzinfo=UTC),
                "q",
                (),
                "a",
                1,
                2,
                3,
                QueryStatus.OK,
            )  # fmt: skip
        )
    assert make_client(Role.EVENTS_MANAGER).get("/v1/assistant/log").status_code == 403
    admin = make_client(Role.ADMIN)
    body = admin.get("/v1/assistant/log").json()
    assert body["total"] == 2 and body["items"][0]["user_id"] == str(user_b)
    filtered = admin.get("/v1/assistant/log", params={"user_id": str(user_a)}).json()
    assert [i["user_name"] for i in filtered["items"]] == ["Ana"]
    assert (
        admin.get("/v1/assistant/log", params={"since": "2026-11-26T10:02:00+00:00"}).json()[
            "total"
        ]
        == 1
    )


def _query(user: UUID, minute: int, question: str = "q") -> QueryRecord:
    return QueryRecord(
        uuid4(), user, datetime(2026, 11, 26, 10, minute, tzinfo=UTC), question, (), "a",
        1, 2, 3, QueryStatus.OK,
    )  # fmt: skip


def _user_id(api: TestClient) -> UUID:
    return api.user_id  # type: ignore[attr-defined,no-any-return]


def test_my_queries_lists_only_my_rows_with_latest_feedback(env: Env, make_client: Any) -> None:
    api = make_client(Role.EVENTS_MANAGER)
    mine = _user_id(api)
    other = uuid4()
    first, second, theirs = _query(mine, 1, "primera"), _query(mine, 2, "segunda"), _query(other, 3)
    env.log.records += [first, second, theirs]
    for value in ("incorrect", "correct"):
        api.post(f"/v1/assistant/queries/{first.id}/feedback", json={"value": value})
    body = api.get("/v1/assistant/my-queries").json()
    assert body["total"] == 2 and [i["question"] for i in body["items"]] == ["segunda", "primera"]
    assert body["items"][0]["feedback"] is None
    assert body["items"][1]["feedback"]["value"] == "correct"
    assert "user_id" not in body["items"][0] and "input_tokens" not in body["items"][0]
    paged = api.get("/v1/assistant/my-queries", params={"page": 2, "page_size": 1}).json()
    assert [i["question"] for i in paged["items"]] == ["primera"] and paged["total"] == 2


def test_my_queries_needs_authentication_and_any_role_can_use_it(
    env: Env, make_client: Any
) -> None:
    assert (
        TestClient(create_app(readiness_check=_no_database))
        .get("/v1/assistant/my-queries")
        .status_code
        == 401
    )
    for role in Role:
        assert make_client(role).get("/v1/assistant/my-queries").status_code == 200


def test_feedback_by_the_author_keeps_every_row_and_the_last_wins(
    env: Env, make_client: Any
) -> None:
    api = make_client(Role.PURCHASING_MANAGER)
    query = _query(_user_id(api), 1)
    env.log.records.append(query)
    url = f"/v1/assistant/queries/{query.id}/feedback"
    created = api.post(url, json={"value": "incorrect", "comment": "  El saldo   no cuadra "})
    assert created.status_code == 201
    assert (
        created.json()["value"] == "incorrect" and created.json()["comment"] == "El saldo no cuadra"
    )
    assert api.post(url, json={"value": "correct"}).status_code == 201
    assert [f.value.value for f in env.feedback.rows] == ["incorrect", "correct"]
    assert api.get("/v1/assistant/my-queries").json()["items"][0]["feedback"]["value"] == "correct"


def test_feedback_from_another_user_or_unknown_query_is_404(env: Env, make_client: Any) -> None:
    query = _query(uuid4(), 1)
    env.log.records.append(query)
    api = make_client(Role.ADMIN)  # ni el administrador valora consultas ajenas
    for query_id in (query.id, uuid4()):
        response = api.post(f"/v1/assistant/queries/{query_id}/feedback", json={"value": "correct"})
        assert (
            response.status_code == 404 and response.json()["code"] == "assistant.query_not_found"
        )
    assert env.feedback.rows == []


@pytest.mark.parametrize(
    "body", [{}, {"value": "maybe"}, {"value": "correct", "comment": "x" * 301}]
)
def test_feedback_invalid_body_is_422(env: Env, make_client: Any, body: dict[str, Any]) -> None:
    response = make_client(Role.ADMIN).post(f"/v1/assistant/queries/{uuid4()}/feedback", json=body)
    assert response.status_code == 422


def test_feedback_requires_authentication() -> None:
    api = TestClient(create_app(readiness_check=_no_database))
    assert (
        api.post(f"/v1/assistant/queries/{uuid4()}/feedback", json={"value": "correct"}).status_code
        == 401
    )


def test_admin_log_includes_the_latest_feedback(env: Env, make_client: Any) -> None:
    author = uuid4()
    graded, plain = _query(author, 1), _query(author, 2)
    env.log.records += [graded, plain]
    env.feedback.rows.append(
        Feedback(
            graded.id, author, FeedbackValue.INCORRECT, "mal", datetime(2026, 11, 26, tzinfo=UTC)
        )
    )
    items = make_client(Role.ADMIN).get("/v1/assistant/log").json()["items"]
    by_id = {i["id"]: i["feedback"] for i in items}
    assert by_id[str(plain.id)] is None
    assert (
        by_id[str(graded.id)]["value"] == "incorrect" and by_id[str(graded.id)]["comment"] == "mal"
    )
