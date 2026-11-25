"""historial de planificación y estado del evento (HU11)

- `commercial_event_changes`: quién, cuándo y qué cambió en la planificación o el estado del
  evento (CA-11.5). Solo inserción: un trigger rechaza UPDATE y DELETE.
- `fields` (JSONB): cada campo cambiado con su antes y después.
- `changed_by` es un usuario de identity: sin FK (regla 3).

Revision ID: 652825952ff5
Revises: 5a3a86214ca7
Create Date: 2026-11-25 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "652825952ff5"
down_revision: str | None = "5a3a86214ca7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "commercial_event_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_by", sa.Uuid(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('PLANNING_UPDATED', 'CONFIRMED', 'STARTED', 'FINISHED', 'CANCELLED')",
            name=op.f("ck_commercial_event_changes_action_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["commercial_events.id"],
            name=op.f("fk_commercial_event_changes_event_id"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_commercial_event_changes")),
    )
    op.create_index(
        op.f("ix_commercial_event_changes_event_id"),
        "commercial_event_changes",
        ["event_id"],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION commercial_event_changes_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'El historial del evento no se puede modificar ni borrar';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER commercial_event_changes_append_only
        BEFORE UPDATE OR DELETE ON commercial_event_changes
        FOR EACH ROW EXECUTE FUNCTION commercial_event_changes_append_only()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER commercial_event_changes_append_only ON commercial_event_changes")
    op.execute("DROP FUNCTION commercial_event_changes_append_only()")
    op.drop_index(
        op.f("ix_commercial_event_changes_event_id"), table_name="commercial_event_changes"
    )
    op.drop_table("commercial_event_changes")
