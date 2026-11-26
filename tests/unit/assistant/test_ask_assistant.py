"""AskAssistant sin base de datos ni red: modelo falso, herramientas y registro en memoria."""

from typing import Any
from uuid import uuid4

import pytest

from local_eventos.modules.assistant.application.errors import (
    AssistantProviderError,
    AssistantRateLimitedError,
    AssistantUnavailableError,
)
from local_eventos.modules.assistant.application.ports.language_model import ToolCall
from local_eventos.modules.assistant.application.tools import (
    Tool,
    ToolInputError,
    ToolRegistry,
)
from local_eventos.modules.assistant.application.use_cases.ask_assistant import (
    INCOMPLETE_ANSWER,
    REFUSAL_ANSWER,
    AskAssistant,
    Asker,
    HistoryTurn,
)
from local_eventos.modules.assistant.domain.query_record import (
    MAX_QUESTIONS_PER_HOUR,
    MAX_TOOL_ROUNDS,
    QueryStatus,
)
from local_eventos.modules.assistant.infrastructure.fake_language_model import (
    FakeLanguageModel,
    calls,
    refuses,
    says,
)
from tests.unit.assistant.fakes import FixedClock, InMemoryQueryLog

SEEN: list[dict[str, Any]] = []


async def _echo(tool_input: dict[str, Any]) -> Any:
    SEEN.append(tool_input)
    if tool_input.get("bad"):
        raise ToolInputError("falta el código")
    return {"saldo_cents": 12_300}


def registry() -> ToolRegistry:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    return ToolRegistry(
        [
            Tool("event_account", "Cuenta", schema, "events:read", _echo),
            Tool("cash_flow", "Caja", schema, "finance:read", _echo),
        ]
    )


ASKER = Asker(uuid4(), frozenset({"events:read"}))


def build(
    script: list[Any],
) -> tuple[AskAssistant, FakeLanguageModel, InMemoryQueryLog, FixedClock]:
    SEEN.clear()
    model = FakeLanguageModel(script)
    log, clock = InMemoryQueryLog(), FixedClock()
    return AskAssistant(model, registry(), log, clock), model, log, clock


async def test_answers_without_tools_and_logs() -> None:
    ask, model, log, _ = build([says("Hola", input_tokens=7, output_tokens=3)])
    result = await ask(ASKER, "¿Qué haces?")
    assert result.answer == "Hola" and result.status is QueryStatus.OK and result.tools == ()
    record = log.records[0]
    assert (record.question, record.answer, record.input_tokens, record.output_tokens) == (
        "¿Qué haces?", "Hola", 7, 3,
    )  # fmt: skip
    assert "[Hoy en Lima: 26/11/2026]" in model.calls[0][-1].text  # la fecha va en el usuario
    assert "2026" not in model.systems[0]  # el sistema es estable (caché)


async def test_executes_tools_and_sends_all_results_in_one_turn() -> None:
    first = calls(
        ToolCall("t1", "event_account", {"code": "EV-1"}), ToolCall("t2", "event_account", {})
    )
    ask, model, log, _ = build([first, says("Saldo S/ 123.00")])
    result = await ask(ASKER, "¿saldo?")
    assert result.answer == "Saldo S/ 123.00"
    assert [t.name for t in result.tools] == ["event_account", "event_account"]
    assert SEEN == [{"code": "EV-1"}, {}]
    followup = model.calls[1][-1]
    assert followup.role == "user" and [r.call_id for r in followup.tool_results] == ["t1", "t2"]
    assert log.records[0].tools[0].input == {"code": "EV-1"}  # auditoría con parámetros


async def test_tool_without_permission_returns_controlled_error() -> None:
    ask, model, log, _ = build([calls(ToolCall("t1", "cash_flow", {})), says("No tienes permiso")])
    await ask(ASKER, "¿caja?")
    result = model.calls[1][-1].tool_results[0]
    assert result.is_error and "sin_permiso" in result.content
    assert SEEN == []  # el handler nunca se ejecutó
    assert log.records[0].tools[0].error is True


async def test_invalid_input_and_unknown_tool_are_errors_for_the_model() -> None:
    script = [
        calls(ToolCall("a", "event_account", {"bad": True}), ToolCall("b", "borrar_todo", {})),
        says("ok"),
    ]
    ask, model, _, _ = build(script)
    await ask(ASKER, "x")
    first, second = model.calls[1][-1].tool_results
    assert first.is_error and "parametros_invalidos" in first.content
    assert second.is_error and "herramienta_desconocida" in second.content


async def test_history_is_sent_before_the_question() -> None:
    ask, model, _, _ = build([says("ok")])
    await ask(
        ASKER, "¿y su saldo?", [HistoryTurn("user", "cliente X"), HistoryTurn("assistant", "ok")]
    )
    assert [m.text[:9] for m in model.calls[0]][:2] == ["cliente X", "ok"]


async def test_stops_after_max_tool_rounds() -> None:
    script = [calls(ToolCall(f"t{i}", "event_account", {})) for i in range(MAX_TOOL_ROUNDS + 1)]
    ask, model, log, _ = build(script)
    result = await ask(ASKER, "x")
    assert result.answer == INCOMPLETE_ANSWER and result.status is QueryStatus.ERROR
    assert len(model.calls) == MAX_TOOL_ROUNDS + 1 and len(SEEN) == MAX_TOOL_ROUNDS
    assert log.records[0].status is QueryStatus.ERROR


async def test_refusal_is_controlled_and_logged() -> None:
    ask, _, log, _ = build([refuses()])
    result = await ask(ASKER, "x")
    assert result.answer == REFUSAL_ANSWER and result.status is QueryStatus.REFUSED
    assert log.records[0].status is QueryStatus.REFUSED


async def test_provider_error_is_logged_and_raised() -> None:
    ask, _, log, _ = build([AssistantProviderError()])
    with pytest.raises(AssistantProviderError):
        await ask(ASKER, "x")
    assert log.records[0].status is QueryStatus.ERROR


async def test_without_model_is_unavailable() -> None:
    ask = AskAssistant(None, registry(), InMemoryQueryLog(), FixedClock())
    with pytest.raises(AssistantUnavailableError):
        await ask(ASKER, "x")


async def test_rate_limit_per_user_per_hour() -> None:
    ask, _, log, clock = build([says("ok")] * (MAX_QUESTIONS_PER_HOUR + 3))
    for _ in range(MAX_QUESTIONS_PER_HOUR):
        await ask(ASKER, "x")
    with pytest.raises(AssistantRateLimitedError):
        await ask(ASKER, "x")
    await ask(Asker(uuid4(), frozenset()), "x")  # otro usuario no se ve afectado
    clock.advance(hours=1, seconds=1)
    await ask(ASKER, "x")  # pasada la hora, vuelve a poder
    assert len(log.records) == MAX_QUESTIONS_PER_HOUR + 2
