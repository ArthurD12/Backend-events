"""Adaptador de Anthropic con un cliente falso: nunca se llama al proveedor real."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from local_eventos.modules.assistant.application.errors import AssistantProviderError
from local_eventos.modules.assistant.application.ports.language_model import (
    ChatMessage,
    StopReason,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from local_eventos.modules.assistant.infrastructure.anthropic_language_model import (
    AnthropicLanguageModel,
)

SPEC = ToolSpec(
    "stock", "Stock", {"type": "object", "properties": {}, "additionalProperties": False}
)


class FakeClient:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.requests: list[dict[str, Any]] = []
        self._response, self._error = response, error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if self._error:
            raise self._error
        return self._response


def response(content: list[Any], stop: str) -> Any:
    usage = SimpleNamespace(
        input_tokens=5, output_tokens=7, cache_read_input_tokens=100, cache_creation_input_tokens=0
    )
    return SimpleNamespace(content=content, stop_reason=stop, usage=usage)


def model(client: FakeClient) -> AnthropicLanguageModel:
    return AnthropicLanguageModel(client)  # type: ignore[arg-type]


async def test_request_follows_the_sdk_rules() -> None:
    client = FakeClient(response([SimpleNamespace(type="text", text="Hola")], "end_turn"))
    reply = await model(client).complete(
        system="sistema", tools=[SPEC], messages=[ChatMessage("user", "hola")]
    )
    request = client.requests[0]
    assert request["model"] == "claude-opus-5-5" and request["max_tokens"] == 16000
    assert request["output_config"] == {"effort": "low"}
    assert request["tool_choice"] == {"type": "auto"}
    assert request["cache_control"] == {"type": "ephemeral"}
    assert request["betas"] == ["server-side-fallback-2026-07-01"]
    assert request["fallbacks"] == "default"
    assert "thinking" not in request and "temperature" not in request
    assert request["tools"][0]["strict"] is True
    assert request["tools"][0]["input_schema"]["additionalProperties"] is False
    assert request["messages"] == [{"role": "user", "content": "hola"}]
    assert (reply.text, reply.stop_reason) == ("Hola", StopReason.END_TURN)
    assert (reply.input_tokens, reply.output_tokens) == (105, 7)


async def test_tool_use_is_parsed_and_results_go_in_one_message() -> None:
    block = SimpleNamespace(type="tool_use", id="t1", name="stock", input={"product": "arroz"})
    client = FakeClient(response([block], "tool_use"))
    reply = await model(client).complete(system="s", tools=[SPEC], messages=[])
    assert reply.tool_calls == (ToolCall("t1", "stock", {"product": "arroz"}),)
    assert reply.stop_reason is StopReason.TOOL_USE and reply.provider_content == [block]

    history = [
        ChatMessage(
            "assistant", tool_calls=reply.tool_calls, provider_content=reply.provider_content
        ),
        ChatMessage("user", tool_results=(ToolResult("t1", "{}"), ToolResult("t2", "x", True))),
    ]
    await model(client).complete(system="s", tools=[SPEC], messages=history)
    sent = client.requests[1]["messages"]
    assert sent[0] == {"role": "assistant", "content": [block]}
    results = sent[1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]
    assert "is_error" not in results[0] and results[1]["is_error"] is True


async def test_refusal_stop_reason() -> None:
    reply = await model(FakeClient(response([], "refusal"))).complete(
        system="s", tools=[], messages=[]
    )
    assert reply.stop_reason is StopReason.REFUSAL


def _status_error(cls: type[anthropic.APIStatusError], code: int) -> anthropic.APIStatusError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("fallo", response=httpx2.Response(code, request=request), body=None)


@pytest.mark.parametrize(
    "error",
    [
        _status_error(anthropic.RateLimitError, 429),
        _status_error(anthropic.InternalServerError, 500),
        anthropic.APIConnectionError(
            request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        ),
    ],
)
async def test_sdk_errors_become_provider_error(error: Exception) -> None:
    with pytest.raises(AssistantProviderError) as raised:
        await model(FakeClient(error=error)).complete(system="s", tools=[], messages=[])
    assert raised.value.code == "assistant.provider_error"
