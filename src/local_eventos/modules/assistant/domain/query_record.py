"""Registro de auditoría de una consulta al asistente (RN33). Solo se inserta, nunca se cambia."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

MAX_QUESTIONS_PER_HOUR = 30  # R-IA-2
MAX_TOOL_ROUNDS = 6  # rondas de herramientas por pregunta (plan §2)


class QueryStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    REFUSED = "refused"


@dataclass(frozen=True)
class ToolUse:
    """Una función de consulta ejecutada, con los parámetros que pidió el modelo."""

    name: str
    input: dict[str, Any]
    error: bool = False


@dataclass(frozen=True)
class QueryRecord:
    id: UUID
    user_id: UUID
    created_at: datetime
    question: str
    tools: tuple[ToolUse, ...]
    answer: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    status: QueryStatus
