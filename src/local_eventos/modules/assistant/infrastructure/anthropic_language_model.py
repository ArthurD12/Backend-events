"""Adaptador del puerto `LanguageModel` con el SDK oficial de Anthropic (ADR 0005).

Reglas del modelo `claude-opus-5-5`: razonamiento adaptativo siempre activo (no se envía
`thinking`), sin `temperature`, `tool_choice` automático (forzar una herramienta da 400) y
herramientas con `strict: true`. El fallback del servidor re-ejecuta la petición si el modelo
la rechaza. `cache_control` a nivel de petición: sistema y herramientas estables.
"""

from collections.abc import Sequence
from typing import Any

import anthropic

from local_eventos.modules.assistant.application.errors import AssistantProviderError
from local_eventos.modules.assistant.application.ports.language_model import (
    ChatMessage,
    ModelReply,
    StopReason,
    ToolCall,
    ToolSpec,
)

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
_STOP_REASONS = {
    "end_turn": StopReason.END_TURN,
    "tool_use": StopReason.TOOL_USE,
    "refusal": StopReason.REFUSAL,
    "max_tokens": StopReason.MAX_TOKENS,
}


class AnthropicLanguageModel:
    def __init__(self, client: anthropic.AsyncAnthropic) -> None:
        self._client = client

    @classmethod
    def from_api_key(cls, api_key: str) -> "AnthropicLanguageModel":
        return cls(anthropic.AsyncAnthropic(api_key=api_key))

    async def complete(
        self, *, system: str, tools: Sequence[ToolSpec], messages: Sequence[ChatMessage]
    ) -> ModelReply:
        params: dict[str, Any] = {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "output_config": {"effort": "low"},
            "cache_control": {"type": "ephemeral"},
            "system": system,
            "tools": [_tool(t) for t in tools],
            "tool_choice": {"type": "auto"},
            "messages": [_message(m) for m in messages],
            "betas": [FALLBACK_BETA],
            "fallbacks": "default",
        }
        try:
            response = await self._client.beta.messages.create(**params)
        except anthropic.RateLimitError as error:
            raise AssistantProviderError(
                "El proveedor del asistente está saturado. Inténtalo en un momento."
            ) from error
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as error:
            raise AssistantProviderError() from error
        return _reply(response)


def _tool(spec: ToolSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "description": spec.description,
        "input_schema": spec.input_schema,
        "strict": True,
    }


def _message(message: ChatMessage) -> dict[str, Any]:
    if message.provider_content is not None:  # turno del asistente: se devuelve tal cual
        return {"role": message.role, "content": message.provider_content}
    if message.tool_results:  # todos los resultados van juntos en un solo mensaje
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": r.call_id,
                    "content": r.content,
                    **({"is_error": True} if r.is_error else {}),
                }
                for r in message.tool_results
            ],
        }
    return {"role": message.role, "content": message.text}


def _reply(response: Any) -> ModelReply:
    text = "".join(b.text for b in response.content if b.type == "text")
    calls = tuple(
        ToolCall(b.id, b.name, dict(b.input)) for b in response.content if b.type == "tool_use"
    )
    stop = _STOP_REASONS.get(response.stop_reason or "end_turn", StopReason.END_TURN)
    if calls and stop is StopReason.END_TURN:
        stop = StopReason.TOOL_USE
    return ModelReply(
        text=text,
        stop_reason=stop,
        tool_calls=calls,
        input_tokens=_total_input(response.usage),
        output_tokens=response.usage.output_tokens,
        provider_content=response.content,
    )


def _total_input(usage: Any) -> int:
    """Entrada total: lo nuevo más lo leído y escrito en el caché de prompt."""
    return sum(
        getattr(usage, name, 0) or 0
        for name in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    )
