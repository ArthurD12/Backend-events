"""crear tabla de consultas del asistente (022)

- `assistant_queries`: auditoría de cada pregunta (usuario, funciones con parámetros, respuesta,
  tokens, duración y estado). Solo inserción: un trigger rechaza UPDATE y DELETE (RN33).

Revision ID: c3a9e5d7f1b2
Revises: ba34931b5de5
Create Date: 2026-11-26 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3a9e5d7f1b2"
down_revision: str | None = "ba34931b5de5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_queries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("tools", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.CheckConstraint(
            "status IN ('ok', 'error', 'refused')",
            name=op.f("ck_assistant_queries_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_queries")),
    )
    op.create_index(
        op.f("ix_assistant_queries_created_at"), "assistant_queries", ["created_at"], unique=False
    )
    op.create_index(
        "ix_assistant_queries_user_id_created_at",
        "assistant_queries",
        ["user_id", "created_at"],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION assistant_queries_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'El historial del asistente no se puede modificar ni borrar';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER assistant_queries_append_only
        BEFORE UPDATE OR DELETE ON assistant_queries
        FOR EACH ROW EXECUTE FUNCTION assistant_queries_append_only()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER assistant_queries_append_only ON assistant_queries")
    op.execute("DROP FUNCTION assistant_queries_append_only()")
    op.drop_index("ix_assistant_queries_user_id_created_at", table_name="assistant_queries")
    op.drop_index(op.f("ix_assistant_queries_created_at"), table_name="assistant_queries")
    op.drop_table("assistant_queries")
