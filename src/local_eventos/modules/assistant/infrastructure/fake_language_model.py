"""Modelo de lenguaje falso para las pruebas: responde lo que se le programa, sin red ni costo.

Nunca se usa en producción ni se llama al proveedor real en las pruebas (AGENTS.md, regla 10).
"""

from collections.abc import Sequence

from local_eventos.modules.assistant.application.ports.language_model import (
    ChatMessage,
    ModelReply,
    StopReason,
    ToolCall,
    ToolSpec,
)


class FakeLanguageModel:
    """Devuelve las respuestas del guion en orden; si un elemento es una excepción, la lanza."""

    def __init__(self, script: Sequence[ModelReply | Exception]) -> None:
        self._script = list(script)
        self.calls: list[list[ChatMessage]] = []
        self.systems: list[str] = []
        self.tool_names: list[list[str]] = []

    async def complete(
        self, *, system: str, tools: Sequence[ToolSpec], messages: Sequence[ChatMessage]
    ) -> ModelReply:
        self.calls.append(list(messages))
        self.systems.append(system)
        self.tool_names.append([t.name for t in tools])
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def says(text: str, *, input_tokens: int = 10, output_tokens: int = 5) -> ModelReply:
    return ModelReply(text, StopReason.END_TURN, (), input_tokens, output_tokens)


def calls(*tool_calls: ToolCall, input_tokens: int = 10, output_tokens: int = 5) -> ModelReply:
    return ModelReply("", StopReason.TOOL_USE, tool_calls, input_tokens, output_tokens)


def refuses() -> ModelReply:
    return ModelReply("", StopReason.REFUSAL)
