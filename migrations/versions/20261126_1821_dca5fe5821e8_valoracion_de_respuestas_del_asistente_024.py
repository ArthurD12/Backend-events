"""valoración de respuestas del asistente (024)

- `assistant_feedback`: el autor de una consulta la marca correcta o incorrecta (con comentario
  opcional). Solo inserción: un trigger rechaza UPDATE y DELETE; la vigente es la de mayor `id`.

Revision ID: dca5fe5821e8
Revises: c3a9e5d7f1b2
Create Date: 2026-11-26 18:21:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "dca5fe5821e8"
down_revision: str | None = "c3a9e5d7f1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_feedback",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("query_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("value", sa.String(length=10), nullable=False),
        sa.Column("comment", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "value IN ('correct', 'incorrect')",
            name=op.f("ck_assistant_feedback_value_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["query_id"],
            ["assistant_queries.id"],
            name=op.f("fk_assistant_feedback_query_id_assistant_queries"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_feedback")),
    )
    op.create_index("ix_assistant_feedback_query_id", "assistant_feedback", ["query_id"])
    op.execute(
        """
        CREATE FUNCTION assistant_feedback_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Las valoraciones del asistente no se pueden modificar ni borrar';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER assistant_feedback_append_only
        BEFORE UPDATE OR DELETE ON assistant_feedback
        FOR EACH ROW EXECUTE FUNCTION assistant_feedback_append_only()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER assistant_feedback_append_only ON assistant_feedback")
    op.execute("DROP FUNCTION assistant_feedback_append_only()")
    op.drop_index("ix_assistant_feedback_query_id", table_name="assistant_feedback")
    op.drop_table("assistant_feedback")
