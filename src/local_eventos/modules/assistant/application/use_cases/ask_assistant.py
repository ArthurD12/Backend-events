"""Caso de uso: responder una pregunta con el modelo y las herramientas de consulta (HU35–HU40).

El bucle de herramientas corre aquí, en el backend: el modelo pide funciones, el backend las
ejecuta con los permisos del usuario y le devuelve los resultados (todos en un solo turno).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from local_eventos.modules.assistant.application.errors import (
    AssistantProviderError,
    AssistantRateLimitedError,
    AssistantUnavailableError,
)
from local_eventos.modules.assistant.application.ports.language_model import (
    ChatMessage,
    LanguageModel,
    StopReason,
    ToolResult,
)
from local_eventos.modules.assistant.application.ports.query_log import Clock, QueryLog
from local_eventos.modules.assistant.application.prompt import SYSTEM_PROMPT
from local_eventos.modules.assistant.application.tools import ToolRegistry
from local_eventos.modules.assistant.domain.query_record import (
    MAX_QUESTIONS_PER_HOUR,
    MAX_TOOL_ROUNDS,
    QueryRecord,
    QueryStatus,
    ToolUse,
)

LIMA = ZoneInfo("America/Lima")
REFUSAL_ANSWER = "No puedo responder esa pregunta. Prueba con otra consulta sobre el sistema."
INCOMPLETE_ANSWER = "No pude completar la consulta. Reformula la pregunta con más detalle."
EMPTY_ANSWER = "No tengo una respuesta para eso."


@dataclass(frozen=True)
class Asker:
    id: UUID
    permissions: frozenset[str]


@dataclass(frozen=True)
class HistoryTurn:
    role: Literal["user", "assistant"]
    text: str


@dataclass(frozen=True)
class AskResult:
    query_id: UUID
    answer: str
    tools: tuple[ToolUse, ...]
    status: QueryStatus


class AskAssistant:
    def __init__(
        self,
        model: LanguageModel | None,
        tools: ToolRegistry,
        log: QueryLog,
        clock: Clock,
    ) -> None:
        self._model = model
        self._tools = tools
        self._log = log
        self._clock = clock

    async def __call__(
        self, asker: Asker, question: str, history: Sequence[HistoryTurn] = ()
    ) -> AskResult:
        if self._model is None:
            raise AssistantUnavailableError()
        started = self._clock.now()
        recent = await self._log.count_since(asker.id, started - timedelta(hours=1))
        if recent >= MAX_QUESTIONS_PER_HOUR:
            raise AssistantRateLimitedError(MAX_QUESTIONS_PER_HOUR)

        today = started.astimezone(LIMA).strftime("%d/%m/%Y")
        messages: list[ChatMessage] = [ChatMessage(t.role, t.text) for t in history]
        messages.append(ChatMessage("user", f"[Hoy en Lima: {today}]\n{question}"))
        used: list[ToolUse] = []
        input_tokens = output_tokens = 0
        status, answer = QueryStatus.ERROR, INCOMPLETE_ANSWER
        failure: AssistantProviderError | None = None

        try:
            for _ in range(MAX_TOOL_ROUNDS + 1):
                reply = await self._model.complete(
                    system=SYSTEM_PROMPT, tools=self._tools.specs(), messages=messages
                )
                input_tokens += reply.input_tokens
                output_tokens += reply.output_tokens
                if reply.stop_reason is StopReason.REFUSAL:
                    status, answer = QueryStatus.REFUSED, REFUSAL_ANSWER
                    break
                if reply.stop_reason is not StopReason.TOOL_USE or not reply.tool_calls:
                    status, answer = QueryStatus.OK, reply.text.strip() or EMPTY_ANSWER
                    break
                if _rounds(messages) >= MAX_TOOL_ROUNDS:
                    break  # sigue pidiendo herramientas: respuesta controlada
                messages.append(
                    ChatMessage(
                        "assistant",
                        reply.text,
                        reply.tool_calls,
                        provider_content=reply.provider_content,
                    )  # fmt: skip
                )
                results: list[ToolResult] = []
                for call in reply.tool_calls:
                    outcome = await self._tools.execute(call.name, call.input, asker.permissions)
                    used.append(ToolUse(call.name, call.input, outcome.is_error))
                    results.append(ToolResult(call.id, outcome.content, outcome.is_error))
                messages.append(ChatMessage("user", tool_results=tuple(results)))
        except AssistantProviderError as error:
            failure, answer = error, str(error)

        query_id = uuid4()
        finished = self._clock.now()
        await self._log.add(
            QueryRecord(
                id=query_id,
                user_id=asker.id,
                created_at=started,
                question=question,
                tools=tuple(used),
                answer=answer,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=int((finished - started).total_seconds() * 1000),
                status=QueryStatus.ERROR if failure else status,
            )
        )
        if failure is not None:
            raise failure
        return AskResult(query_id=query_id, answer=answer, tools=tuple(used), status=status)


def _rounds(messages: Sequence[ChatMessage]) -> int:
    return sum(1 for m in messages if m.role == "assistant" and m.tool_calls)
