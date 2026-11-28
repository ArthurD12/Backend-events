"""crear tablas de asistencia del personal (HU18)

Tablas de la HU18: estado vigente de asistencia y su auditoría append-only.

- `staff_attendance`: una sola fila por asignación (la PK es `assignment_id`).
  `assignment_id` apunta a `staff_assignments` con `ON DELETE RESTRICT`.
  `recorded_by` es un usuario de `identity` sin FK (AGENTS.md, regla 3). Un
  trigger `BEFORE DELETE` rechaza el borrado físico: la asistencia se corrige,
  nunca se elimina.
- `staff_attendance_audit`: una fila por `RECORDED`/`CORRECTED`. El CHECK
  compuesto replica R-ATT-7/R-ATT-22: el primer registro no lleva valor anterior
  ni motivo; la corrección exige valor anterior distinto y motivo recortado de
  1..500 caracteres. Un trigger `BEFORE UPDATE OR DELETE` la hace append-only.

Revision ID: 7c1f2a9d4e60
Revises: b959d55b8430
Create Date: 2026-11-28 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c1f2a9d4e60"
down_revision: str | None = "b959d55b8430"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_VALID = "status IN ('ATTENDED', 'NOT_ATTENDED')"
_AUDIT_PREVIOUS_STATUS_VALID = (
    "previous_status IS NULL OR previous_status IN ('ATTENDED', 'NOT_ATTENDED')"
)
_AUDIT_NEW_STATUS_VALID = "new_status IN ('ATTENDED', 'NOT_ATTENDED')"
_AUDIT_RULE_VALID = (
    "(action = 'RECORDED' AND previous_status IS NULL AND reason IS NULL)"
    " OR (action = 'CORRECTED' AND previous_status IS NOT NULL"
    " AND previous_status <> new_status AND reason IS NOT NULL"
    " AND btrim(reason) <> '' AND char_length(btrim(reason)) <= 500)"
)


def upgrade() -> None:
    op.create_table(
        "staff_attendance",
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(_STATUS_VALID, name=op.f("ck_staff_attendance_status_valid")),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["staff_assignments.id"],
            name=op.f("fk_staff_attendance_assignment_id"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("assignment_id", name=op.f("pk_staff_attendance")),
    )

    op.create_table(
        "staff_attendance_audit",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=9), nullable=False),
        sa.Column("previous_status", sa.String(length=12), nullable=True),
        sa.Column("new_status", sa.String(length=12), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('RECORDED', 'CORRECTED')",
            name=op.f("ck_staff_attendance_audit_action_valid"),
        ),
        sa.CheckConstraint(
            _AUDIT_PREVIOUS_STATUS_VALID,
            name=op.f("ck_staff_attendance_audit_previous_status_valid"),
        ),
        sa.CheckConstraint(
            _AUDIT_NEW_STATUS_VALID,
            name=op.f("ck_staff_attendance_audit_new_status_valid"),
        ),
        sa.CheckConstraint(
            _AUDIT_RULE_VALID,
            name=op.f("ck_staff_attendance_audit_reason_and_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["staff_assignments.id"],
            name=op.f("fk_staff_attendance_audit_assignment_id"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_attendance_audit")),
    )
    op.create_index(
        "ix_staff_attendance_audit_assignment_occurred",
        "staff_attendance_audit",
        ["assignment_id", "occurred_at"],
        unique=False,
    )

    # Regla 5 de AGENTS.md: la auditoría es append-only. Rechaza UPDATE y DELETE.
    op.execute(
        """
        CREATE FUNCTION staff_attendance_audit_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'La auditoría de asistencia no se modifica ni se borra'
                USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_attendance_audit_append_only
        BEFORE UPDATE OR DELETE ON staff_attendance_audit
        FOR EACH ROW EXECUTE FUNCTION staff_attendance_audit_append_only()
        """
    )

    # La asistencia no se borra: se corrige dejando traza (R-ATT-6/R-ATT-7).
    op.execute(
        """
        CREATE FUNCTION staff_attendance_no_delete() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'La asistencia no se borra físicamente: se corrige'
                USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER staff_attendance_no_delete
        BEFORE DELETE ON staff_attendance
        FOR EACH ROW EXECUTE FUNCTION staff_attendance_no_delete()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER staff_attendance_no_delete ON staff_attendance")
    op.execute("DROP FUNCTION staff_attendance_no_delete()")
    op.execute("DROP TRIGGER staff_attendance_audit_append_only ON staff_attendance_audit")
    op.execute("DROP FUNCTION staff_attendance_audit_append_only()")
    op.drop_index(
        "ix_staff_attendance_audit_assignment_occurred",
        table_name="staff_attendance_audit",
    )
    op.drop_table("staff_attendance_audit")
    op.drop_table("staff_attendance")
