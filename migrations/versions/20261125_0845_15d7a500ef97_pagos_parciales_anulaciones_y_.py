"""pagos parciales, anulaciones y movimientos de caja (HU19–HU22)

- `ledger_payments`: número `PAG-AAAA-NNNN` (los pagos existentes lo reciben aquí, por orden de
  registro) y tipo `INSTALLMENT` (pago parcial).
- Anulaciones de pagos y movimientos en tablas aparte; ingresos y egresos de caja.
- Las cuatro tablas son de solo inserción (AGENTS.md, regla 5).

Revision ID: 15d7a500ef97
Revises: a4f88017b782
Create Date: 2026-11-25 08:45:28.900061
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "15d7a500ef97"
down_revision: str | None = "a4f88017b782"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APPEND_ONLY = ("ledger_payment_voids", "ledger_movements", "ledger_movement_voids")


def upgrade() -> None:
    op.create_table(
        "ledger_payment_counters",
        sa.Column("year", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("last", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("year", name=op.f("pk_ledger_payment_counters")),
    )

    # Número de los pagos ya registrados, por año (en Lima) y orden de registro.
    op.add_column("ledger_payments", sa.Column("number", sa.String(length=20), nullable=True))
    # Excepción única y deliberada a la regla 5: el trigger de solo inserción se desactiva SOLO
    # para este relleno y se reactiva enseguida, dentro de la misma transacción de la migración.
    op.execute("ALTER TABLE ledger_payments DISABLE TRIGGER ledger_payments_append_only")
    op.execute(
        """
        UPDATE ledger_payments AS p
        SET number = 'PAG-' || n.year || '-' || lpad(n.seq::text, 4, '0')
        FROM (
            SELECT id,
                   EXTRACT(YEAR FROM recorded_at AT TIME ZONE 'America/Lima')::int AS year,
                   row_number() OVER (
                       PARTITION BY EXTRACT(YEAR FROM recorded_at AT TIME ZONE 'America/Lima')
                       ORDER BY recorded_at, id
                   ) AS seq
            FROM ledger_payments
        ) AS n
        WHERE p.id = n.id
        """
    )
    op.execute("ALTER TABLE ledger_payments ENABLE TRIGGER ledger_payments_append_only")
    op.execute(
        """
        INSERT INTO ledger_payment_counters (year, last)
        SELECT split_part(number, '-', 2)::int, max(split_part(number, '-', 3)::int)
        FROM ledger_payments GROUP BY 1
        """
    )
    op.alter_column("ledger_payments", "number", nullable=False)
    op.create_unique_constraint(op.f("uq_ledger_payments_number"), "ledger_payments", ["number"])

    op.alter_column(
        "ledger_payments",
        "kind",
        type_=sa.String(length=11),
        existing_type=sa.String(length=10),
        existing_nullable=False,
    )
    op.drop_constraint(op.f("ck_ledger_payments_kind_valid"), "ledger_payments", type_="check")
    op.create_check_constraint(
        "kind_valid", "ledger_payments", "kind IN ('ADVANCE', 'INSTALLMENT', 'REFUND')"
    )
    op.create_index(op.f("ix_ledger_payments_paid_on"), "ledger_payments", ["paid_on"])

    op.create_table(
        "ledger_payment_voids",
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("voided_by", sa.Uuid(), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["ledger_payments.id"],
            name=op.f("fk_ledger_payment_voids_payment_id"),
        ),
        sa.PrimaryKeyConstraint("payment_id", name=op.f("pk_ledger_payment_voids")),
    )
    op.create_table(
        "ledger_movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("category", sa.String(length=15), nullable=False),
        sa.Column("concept", sa.String(length=200), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="PEN", nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name=op.f("ck_ledger_movements_amount_positive")),
        sa.CheckConstraint(
            "(type = 'INCOME' AND category = 'OTHER_INCOME') OR (type = 'EXPENSE' AND category IN"
            " ('SUPPLIES', 'STAFF', 'TRANSPORT', 'OTHER_EXPENSE'))",
            name=op.f("ck_ledger_movements_category_valid"),
        ),
        sa.CheckConstraint(
            "method IN ('CASH', 'TRANSFER', 'CARD', 'YAPE_PLIN')",
            name=op.f("ck_ledger_movements_method_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_movements")),
    )
    op.create_index(op.f("ix_ledger_movements_occurred_on"), "ledger_movements", ["occurred_on"])
    op.create_index(op.f("ix_ledger_movements_event_id"), "ledger_movements", ["event_id"])
    op.create_table(
        "ledger_movement_voids",
        sa.Column("movement_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("voided_by", sa.Uuid(), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["movement_id"],
            ["ledger_movements.id"],
            name=op.f("fk_ledger_movement_voids_movement_id"),
        ),
        sa.PrimaryKeyConstraint("movement_id", name=op.f("pk_ledger_movement_voids")),
    )

    # AGENTS.md, regla 5 (RN17): anulaciones y movimientos solo se insertan.
    op.execute(
        """
        CREATE FUNCTION ledger_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'El dinero no se modifica ni se borra: se anula (RN17)';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in _APPEND_ONLY:
        op.execute(
            f"""
            CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION ledger_append_only()
            """
        )


def downgrade() -> None:
    for table in _APPEND_ONLY:
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.execute("DROP FUNCTION ledger_append_only()")
    op.drop_table("ledger_movement_voids")
    op.drop_index(op.f("ix_ledger_movements_event_id"), table_name="ledger_movements")
    op.drop_index(op.f("ix_ledger_movements_occurred_on"), table_name="ledger_movements")
    op.drop_table("ledger_movements")
    op.drop_table("ledger_payment_voids")
    op.drop_index(op.f("ix_ledger_payments_paid_on"), table_name="ledger_payments")
    # Bajar con pagos parciales registrados falla aquí a propósito: no se borra dinero.
    op.drop_constraint(op.f("ck_ledger_payments_kind_valid"), "ledger_payments", type_="check")
    op.create_check_constraint("kind_valid", "ledger_payments", "kind IN ('ADVANCE', 'REFUND')")
    op.alter_column(
        "ledger_payments",
        "kind",
        type_=sa.String(length=10),
        existing_type=sa.String(length=11),
        existing_nullable=False,
    )
    op.drop_constraint(op.f("uq_ledger_payments_number"), "ledger_payments", type_="unique")
    op.drop_column("ledger_payments", "number")
    op.drop_table("ledger_payment_counters")
