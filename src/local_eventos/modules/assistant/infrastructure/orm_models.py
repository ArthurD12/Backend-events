"""Tabla del asistente en PostgreSQL. Prefijo `assistant_` por ser de este módulo.

Sin FK al usuario: los módulos se relacionan por ID (AGENTS.md, regla 3).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from local_eventos.shared.infrastructure.orm import Base


class QueryRow(Base):
    """Auditoría de consultas (RN33). Un trigger de la migración impide UPDATE y DELETE."""

    __tablename__ = "assistant_queries"
    __table_args__ = (
        CheckConstraint("status IN ('ok', 'error', 'refused')", name="status_valid"),
        Index("ix_assistant_queries_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    question: Mapped[str] = mapped_column(Text)
    tools: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    answer: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10))
