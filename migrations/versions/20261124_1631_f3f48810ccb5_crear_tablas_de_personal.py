"""crear tablas de personal

Tablas de la HU15 (trabajadores). La baja es lógica (`status`), nunca borrado
físico; la auditoría es append-only y su trigger lo garantiza en la base, igual
que `identity_access_log` y `ledger_payments`.

Revision ID: f3f48810ccb5
Revises: d0f713f5dc65
Create Date: 2026-11-24 16:31:44.541007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3f48810ccb5"
down_revision: str | None = "d0f713f5dc65"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_workers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("document_type", sa.String(length=3), nullable=False),
        sa.Column("document_number", sa.String(length=12), nullable=False),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("worker_function", sa.String(length=15), nullable=True),
        sa.Column("function_description", sa.Text(), nullable=True),
        sa.Column("worker_type", sa.String(length=8), nullable=True),
        sa.Column("rate_cents", sa.Integer(), nullable=True),
        sa.Column(
            "overtime_applies",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("overtime_rate_cents", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=8),
            server_default=sa.text("'ACTIVE'"),
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
        sa.CheckConstraint("btrim(name) <> ''", name=op.f("ck_staff_workers_name_not_empty")),
        sa.CheckConstraint(
            "(document_type = 'DNI' AND document_number ~ '^[0-9]{8}$')"
            " OR (document_type = 'CE' AND document_number ~ '^[0-9]{9,12}$')",
            name=op.f("ck_staff_workers_document_valid"),
        ),
        sa.CheckConstraint(
            "phone IS NULL OR phone ~ '^[0-9]+$'",
            name=op.f("ck_staff_workers_phone_digits"),
        ),
        sa.CheckConstraint(
            "worker_function IS NULL OR worker_function IN"
            " ('COOK', 'WAITER', 'BARTENDER', 'ASSISTANT', 'COORDINATOR', 'OTHER')",
            name=op.f("ck_staff_workers_function_valid"),
        ),
        sa.CheckConstraint(
            "(worker_function = 'OTHER' AND function_description IS NOT NULL"
            " AND btrim(function_description) <> '')"
            " OR (worker_function IS DISTINCT FROM 'OTHER' AND function_description IS NULL)",
            name=op.f("ck_staff_workers_function_description_valid"),
        ),
        sa.CheckConstraint(
            "worker_type IS NULL OR worker_type IN ('FIXED', 'EVENTUAL')",
            name=op.f("ck_staff_workers_worker_type_valid"),
        ),
        sa.CheckConstraint(
            "rate_cents IS NULL OR rate_cents >= 0",
            name=op.f("ck_staff_workers_rate_not_negative"),
        ),
        sa.CheckConstraint(
            "(overtime_applies AND overtime_rate_cents IS NOT NULL AND overtime_rate_cents > 0)"
            " OR (NOT overtime_applies AND overtime_rate_cents IS NULL)",
            name=op.f("ck_staff_workers_overtime_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE')",
            name=op.f("ck_staff_workers_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_workers")),
        sa.UniqueConstraint(
            "document_type", "document_number", name="uq_staff_workers_document"
        ),
    )
    op.create_index(
        "ix_staff_workers_status_function",
        "staff_workers",
        ["status", "worker_function"],
        unique=False,
    )
    op.create_index(
        "ix_staff_workers_function",
        "staff_workers",
        ["worker_function"],
        unique=False,
    )
    op.create_index(
        "ix_staff_workers_document_number",
        "staff_workers",
        ["document_number"],
        unique=False,
    )
    op.create_index(
        "ix_staff_workers_name_lower",
        "staff_workers",
        [sa.literal_column("lower(name)")],
        unique=False,
    )

    op.create_table(
        "staff_worker_audit",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("worker_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=12), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.Uuid(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('CREATED', 'UPDATED', 'ACTIVATED', 'DEACTIVATED')",
            name=op.f("ck_staff_worker_audit_action_valid"),
        ),
        sa.CheckConstraint(
            "reason IS NULL OR (action IN ('ACTIVATED', 'DEACTIVATED') AND btrim(reason) <> '')",
            name=op.f("ck_staff_worker_audit_reason_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["staff_workers.id"],
            name=op.f("fk_staff_worker_audit_worker_id"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_worker_audit")),
    )
    op.create_index(
        "ix_staff_worker_audit_worker_changed",
        "staff_worker_audit",
        ["worker_id", "changed_at"],
        unique=False,
    )

    # AGENTS.md, regla 5: la auditoría es de solo inserción. La base rechaza
    # cualquier UPDATE o DELETE, aunque venga del propio usuario de la aplicación.
    op.execute(
        """
        CREATE FUNCTION staff_worker_audit_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'La auditoría del personal no se modifica ni se borra';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_worker_audit_append_only
        BEFORE UPDATE OR DELETE ON staff_worker_audit
        FOR EACH ROW EXECUTE FUNCTION staff_worker_audit_append_only()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER staff_worker_audit_append_only ON staff_worker_audit")
    op.execute("DROP FUNCTION staff_worker_audit_append_only()")
    op.drop_index("ix_staff_worker_audit_worker_changed", table_name="staff_worker_audit")
    op.drop_table("staff_worker_audit")
    op.drop_index("ix_staff_workers_name_lower", table_name="staff_workers")
    op.drop_index("ix_staff_workers_document_number", table_name="staff_workers")
    op.drop_index("ix_staff_workers_function", table_name="staff_workers")
    op.drop_index("ix_staff_workers_status_function", table_name="staff_workers")
    op.drop_table("staff_workers")
