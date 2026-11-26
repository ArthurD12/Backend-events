"""crear tablas de asignaciones

Tablas de la HU17 (asignaciones de personal). La anulación es lógica (`status`),
nunca borrado físico; la auditoría es append-only. El no-solape se garantiza con
una restricción de exclusión de PostgreSQL sobre `(worker_id, tstzrange(...))`,
que requiere la extensión `btree_gist` (ADR 0005). El `downgrade` no elimina la
extensión porque puede usarla otro esquema o una migración posterior.

Revision ID: 8df99a56ff18
Revises: 6900ec1af5f8
Create Date: 2026-11-26 10:11:55.893933
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8df99a56ff18"
down_revision: str | None = "6900ec1af5f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION_DESCRIPTION_VALID = (
    "(worker_function = 'OTHER' AND function_description IS NOT NULL"
    " AND btrim(function_description) <> '')"
    " OR (worker_function IS DISTINCT FROM 'OTHER' AND function_description IS NULL)"
)
_AUDIT_REASON_VALID = (
    "reason IS NULL OR (action IN ('UPDATED', 'CANCELLED') AND btrim(reason) <> '')"
)
_AUDIT_SNAPSHOTS_VALID = (
    "(action = 'UPDATED') = (previous_values IS NOT NULL AND new_values IS NOT NULL)"
)


def upgrade() -> None:
    # ADR 0005: el operador de igualdad para `uuid` en GiST lo aporta btree_gist.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "staff_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.Uuid(), nullable=False),
        sa.Column("worker_function", sa.String(length=15), nullable=False),
        sa.Column("function_description", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pay_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False),
        sa.Column(
            "occupies",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("end_at > start_at", name=op.f("ck_staff_assignments_window_valid")),
        sa.CheckConstraint("pay_cents >= 0", name=op.f("ck_staff_assignments_pay_not_negative")),
        sa.CheckConstraint("currency = 'PEN'", name=op.f("ck_staff_assignments_currency_pen")),
        sa.CheckConstraint(
            "worker_function IN"
            " ('COOK', 'WAITER', 'BARTENDER', 'ASSISTANT', 'COORDINATOR', 'OTHER')",
            name=op.f("ck_staff_assignments_function_valid"),
        ),
        sa.CheckConstraint(
            _FUNCTION_DESCRIPTION_VALID,
            name=op.f("ck_staff_assignments_function_description_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'CANCELLED')",
            name=op.f("ck_staff_assignments_status_valid"),
        ),
        sa.CheckConstraint(
            "(status = 'CANCELLED' AND NOT occupies) OR (status = 'ACTIVE')",
            name=op.f("ck_staff_assignments_occupies_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["staff_workers.id"],
            name=op.f("fk_staff_assignments_worker_id"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_assignments")),
    )
    op.create_index(
        "ix_staff_assignments_event_start",
        "staff_assignments",
        ["event_id", "start_at"],
        unique=False,
    )
    op.create_index(
        "ix_staff_assignments_worker_start",
        "staff_assignments",
        ["worker_id", "start_at"],
        unique=False,
    )

    op.create_table(
        "staff_assignment_audit",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=9), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "action IN ('CREATED', 'UPDATED', 'CANCELLED')",
            name=op.f("ck_staff_assignment_audit_action_valid"),
        ),
        sa.CheckConstraint(
            _AUDIT_REASON_VALID,
            name=op.f("ck_staff_assignment_audit_reason_valid"),
        ),
        sa.CheckConstraint(
            _AUDIT_SNAPSHOTS_VALID,
            name=op.f("ck_staff_assignment_audit_snapshots_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["staff_assignments.id"],
            name=op.f("fk_staff_assignment_audit_assignment_id"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_assignment_audit")),
    )
    op.create_index(
        "ix_staff_assignment_audit_assignment_occurred",
        "staff_assignment_audit",
        ["assignment_id", "occurred_at"],
        unique=False,
    )

    # La restricción de exclusión es la fuente de verdad del no-solape (R-ASG-3).
    # El predicado parcial permite conservar asignaciones de eventos cancelados
    # sin que ocupen al trabajador (R-ASG-12).
    op.execute(
        """
        ALTER TABLE staff_assignments
        ADD CONSTRAINT staff_assignments_no_overlap
        EXCLUDE USING gist (
            worker_id WITH =,
            tstzrange(start_at, end_at, '[)') WITH &&
        ) WHERE (occupies)
        """
    )

    # Regla 5 de AGENTS.md: ledger e inventario append-only; la auditoría de
    # asignaciones también lo es. Rechaza cualquier UPDATE o DELETE.
    op.execute(
        """
        CREATE FUNCTION staff_assignment_audit_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'La auditoría de asignaciones no se modifica ni se borra'
                USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_assignment_audit_append_only
        BEFORE UPDATE OR DELETE ON staff_assignment_audit
        FOR EACH ROW EXECUTE FUNCTION staff_assignment_audit_append_only()
        """
    )

    # La asignación no se borra: se anula lógicamente (R-ASG-2).
    op.execute(
        """
        CREATE FUNCTION staff_assignments_no_delete() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'La asignación no se borra físicamente: se anula'
                USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_assignments_no_delete
        BEFORE DELETE ON staff_assignments
        FOR EACH ROW EXECUTE FUNCTION staff_assignments_no_delete()
        """
    )

    # Las claves de la asignación son inmutables y una anulada no se reactiva.
    op.execute(
        """
        CREATE FUNCTION staff_assignments_immutable_keys() RETURNS trigger AS $$
        BEGIN
            IF NEW.worker_id <> OLD.worker_id OR NEW.event_id <> OLD.event_id THEN
                RAISE EXCEPTION 'Las claves de la asignación son inmutables'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF OLD.status = 'CANCELLED' AND NEW.status = 'ACTIVE' THEN
                RAISE EXCEPTION 'Una asignación anulada no se reactiva'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_assignments_immutable_keys
        BEFORE UPDATE ON staff_assignments
        FOR EACH ROW EXECUTE FUNCTION staff_assignments_immutable_keys()
        """
    )


def downgrade() -> None:
    # No se elimina btree_gist: puede usarla otro esquema (ADR 0005).
    op.execute("DROP TRIGGER staff_assignments_immutable_keys ON staff_assignments")
    op.execute("DROP TRIGGER staff_assignments_no_delete ON staff_assignments")
    op.execute("DROP FUNCTION staff_assignments_immutable_keys()")
    op.execute("DROP FUNCTION staff_assignments_no_delete()")
    op.execute("DROP TRIGGER staff_assignment_audit_append_only ON staff_assignment_audit")
    op.execute("DROP FUNCTION staff_assignment_audit_append_only()")
    op.drop_index(
        "ix_staff_assignment_audit_assignment_occurred",
        table_name="staff_assignment_audit",
    )
    op.drop_table("staff_assignment_audit")
    op.drop_index("ix_staff_assignments_worker_start", table_name="staff_assignments")
    op.drop_index("ix_staff_assignments_event_start", table_name="staff_assignments")
    op.drop_table("staff_assignments")
