"""crear tablas de disponibilidad (HU16)

Tablas de la HU16: ventanas de indisponibilidad del personal y su auditoría.

- `staff_unavailabilities`: la anulación es lógica (`status`), nunca borrado
  físico. `worker_id` apunta a `staff_workers` con `ON DELETE RESTRICT`. Se
  permiten indisponibilidades solapadas (son informativas); no hay restricción
  de exclusión ni `UNIQUE` por trabajador/fecha.
- `staff_unavailabilities_audit`: una fila por alta, edición o anulación. Solo
  se inserta: un trigger rechaza cualquier `UPDATE` o `DELETE`.

Triggers de `staff_unavailabilities`: no borrado físico e inmutabilidad de
`worker_id` (una anulada no se reactiva). Mismo patrón que `staff_assignments`
(HU17, migración `8df99a56ff18`).

Revision ID: b959d55b8430
Revises: 8df99a56ff18
Create Date: 2026-11-27 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b959d55b8430"
down_revision: str | None = "8df99a56ff18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DESCRIPTION_VALID = (
    "(kind = 'OTHER' AND description IS NOT NULL AND btrim(description) <> '')"
    " OR (kind IS DISTINCT FROM 'OTHER' AND description IS NULL)"
)
_AUDIT_REASON_VALID = (
    "(action = 'CREATED' AND reason IS NULL)"
    " OR (action IN ('UPDATED', 'CANCELLED')"
    " AND reason IS NOT NULL AND btrim(reason) <> '')"
)
_AUDIT_SNAPSHOTS_VALID = (
    "(action = 'UPDATED') = (previous_values IS NOT NULL AND new_values IS NOT NULL)"
)


def upgrade() -> None:
    op.create_table(
        "staff_unavailabilities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False),
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
        sa.CheckConstraint(
            "end_at > start_at", name=op.f("ck_staff_unavailabilities_window_valid")
        ),
        sa.CheckConstraint(
            "kind IN ('VACATION', 'LEAVE', 'REST', 'OTHER')",
            name=op.f("ck_staff_unavailabilities_kind_valid"),
        ),
        sa.CheckConstraint(
            _DESCRIPTION_VALID,
            name=op.f("ck_staff_unavailabilities_description_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'CANCELLED')",
            name=op.f("ck_staff_unavailabilities_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["staff_workers.id"],
            name=op.f("fk_staff_unavailabilities_worker_id"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_unavailabilities")),
    )
    op.create_index(
        "ix_staff_unavailabilities_worker_start",
        "staff_unavailabilities",
        ["worker_id", "start_at"],
        unique=False,
    )
    op.create_index(
        "ix_staff_unavailabilities_start_end",
        "staff_unavailabilities",
        ["start_at", "end_at"],
        unique=False,
    )

    op.create_table(
        "staff_unavailabilities_audit",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("unavailability_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=9), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "action IN ('CREATED', 'UPDATED', 'CANCELLED')",
            name=op.f("ck_staff_unavailabilities_audit_action_valid"),
        ),
        sa.CheckConstraint(
            _AUDIT_REASON_VALID,
            name=op.f("ck_staff_unavailabilities_audit_reason_valid"),
        ),
        sa.CheckConstraint(
            _AUDIT_SNAPSHOTS_VALID,
            name=op.f("ck_staff_unavailabilities_audit_snapshots_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["unavailability_id"],
            ["staff_unavailabilities.id"],
            name=op.f("fk_staff_unavailabilities_audit_unavailability_id"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_unavailabilities_audit")),
    )
    op.create_index(
        "ix_staff_unavailabilities_audit_unavailability_occurred",
        "staff_unavailabilities_audit",
        ["unavailability_id", "occurred_at"],
        unique=False,
    )

    # Regla 5 de AGENTS.md: la auditoría es append-only. Rechaza UPDATE y DELETE.
    op.execute(
        """
        CREATE FUNCTION staff_unavailabilities_audit_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'La auditoría de indisponibilidades no se modifica ni se borra'
                USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_unavailabilities_audit_append_only
        BEFORE UPDATE OR DELETE ON staff_unavailabilities_audit
        FOR EACH ROW EXECUTE FUNCTION staff_unavailabilities_audit_append_only()
        """
    )

    # La indisponibilidad no se borra: se anula lógicamente (R-DIS-6).
    op.execute(
        """
        CREATE FUNCTION staff_unavailabilities_no_delete() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'La indisponibilidad no se borra físicamente: se anula'
                USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_unavailabilities_no_delete
        BEFORE DELETE ON staff_unavailabilities
        FOR EACH ROW EXECUTE FUNCTION staff_unavailabilities_no_delete()
        """
    )

    # `worker_id` es inmutable y una anulada no se reactiva.
    op.execute(
        """
        CREATE FUNCTION staff_unavailabilities_immutable_keys() RETURNS trigger AS $$
        BEGIN
            IF NEW.worker_id <> OLD.worker_id THEN
                RAISE EXCEPTION 'El trabajador de la indisponibilidad es inmutable'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF OLD.status = 'CANCELLED' AND NEW.status = 'ACTIVE' THEN
                RAISE EXCEPTION 'Una indisponibilidad anulada no se reactiva'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_unavailabilities_immutable_keys
        BEFORE UPDATE ON staff_unavailabilities
        FOR EACH ROW EXECUTE FUNCTION staff_unavailabilities_immutable_keys()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER staff_unavailabilities_immutable_keys ON staff_unavailabilities")
    op.execute("DROP TRIGGER staff_unavailabilities_no_delete ON staff_unavailabilities")
    op.execute("DROP FUNCTION staff_unavailabilities_immutable_keys()")
    op.execute("DROP FUNCTION staff_unavailabilities_no_delete()")
    op.execute(
        "DROP TRIGGER staff_unavailabilities_audit_append_only ON staff_unavailabilities_audit"
    )
    op.execute("DROP FUNCTION staff_unavailabilities_audit_append_only()")
    op.drop_index(
        "ix_staff_unavailabilities_audit_unavailability_occurred",
        table_name="staff_unavailabilities_audit",
    )
    op.drop_table("staff_unavailabilities_audit")
    op.drop_index("ix_staff_unavailabilities_start_end", table_name="staff_unavailabilities")
    op.drop_index("ix_staff_unavailabilities_worker_start", table_name="staff_unavailabilities")
    op.drop_table("staff_unavailabilities")
