"""Valoración de una respuesta del asistente por quien la preguntó (HU40). Solo se inserta."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

MAX_COMMENT_LENGTH = 300  # R-IA-8


class FeedbackValue(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"


@dataclass(frozen=True)
class Feedback:
    query_id: UUID
    user_id: UUID
    value: FeedbackValue
    comment: str | None
    created_at: datetime
