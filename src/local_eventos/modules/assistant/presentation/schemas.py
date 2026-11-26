"""Esquemas de la API del asistente."""

from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.assistant.application.use_cases.search_queries import QueryPage
from local_eventos.modules.assistant.domain.query_record import QueryRecord, ToolUse


class HistoryTurnIn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[HistoryTurnIn] = Field(
        default_factory=list,
        max_length=10,
        description="Turnos previos de la sesión de chat (el backend no guarda la conversación)",
    )


class ToolUseOut(BaseModel):
    name: str = Field(description="Función de consulta ejecutada")
    input: dict[str, Any] = Field(description="Parámetros con que se ejecutó")
    error: bool

    @classmethod
    def from_use(cls, use: ToolUse) -> Self:
        return cls(name=use.name, input=use.input, error=use.error)


class AskOut(BaseModel):
    answer: str
    tools: list[ToolUseOut] = Field(description="Funciones consultadas (transparencia)")


class StatusOut(BaseModel):
    available: bool = Field(description="Falso si no hay clave del proveedor configurada")


class QueryLogEntryOut(BaseModel):
    id: UUID
    user_id: UUID
    user_name: str | None
    created_at: datetime
    question: str
    tools: list[ToolUseOut]
    answer: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    status: Literal["ok", "error", "refused"]

    @classmethod
    def from_record(cls, record: QueryRecord, user_name: str | None) -> Self:
        return cls(
            id=record.id,
            user_id=record.user_id,
            user_name=user_name,
            created_at=record.created_at,
            question=record.question,
            tools=[ToolUseOut.from_use(t) for t in record.tools],
            answer=record.answer,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            duration_ms=record.duration_ms,
            status=record.status.value,
        )


class QueryLogPageOut(BaseModel):
    items: list[QueryLogEntryOut]
    total: int
    page: int
    page_size: int

    @classmethod
    def from_page(cls, page: QueryPage, names: dict[UUID, str]) -> Self:
        return cls(
            items=[QueryLogEntryOut.from_record(r, names.get(r.user_id)) for r in page.items],
            total=page.total,
            page=page.page,
            page_size=page.page_size,
        )
