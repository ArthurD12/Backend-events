"""Puerto del modelo de lenguaje. Cambiar de proveedor no toca el dominio ni las herramientas.

Los tipos son neutrales: el adaptador los traduce al formato de su proveedor. Los adaptadores
lanzan `AssistantProviderError` si el proveedor falla.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class ChatMessage:
    """Un turno. El del asistente puede traer `tool_calls`; el siguiente del usuario, los
    `tool_results` de TODAS esas llamadas. `provider_content` es opaco: el adaptador lo devuelve
    tal cual al proveedor (bloques de razonamiento firmados) y el resto lo ignora."""

    role: Literal["user", "assistant"]
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()
    provider_content: Any = None


class StopReason(StrEnum):
    END_TURN = "end_turn"
    TOOL_USE = "tool_use"
    REFUSAL = "refusal"
    MAX_TOKENS = "max_tokens"


@dataclass(frozen=True)
class ModelReply:
    text: str
    stop_reason: StopReason
    tool_calls: tuple[ToolCall, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0
    provider_content: Any = None


class LanguageModel(Protocol):
    async def complete(
        self, *, system: str, tools: Sequence[ToolSpec], messages: Sequence[ChatMessage]
    ) -> ModelReply: ...
