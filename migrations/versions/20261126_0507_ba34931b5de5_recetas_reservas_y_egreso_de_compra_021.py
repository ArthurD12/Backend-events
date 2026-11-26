"""recetas, reservas y egreso de compra (021)

- `inventory_recipe_lines`: insumos por servicio del catálogo (sin FK a catalog).
- `inventory_reservations`: apartados por evento; una vigente por evento y producto.
- `purchasing_purchases.expense_movement_id`: único, para registrar el egreso una sola vez. El
  trigger de compras ahora permite fijar ese campo (NULL → valor) en una compra recibida.

Revision ID: ba34931b5de5
Revises: 6900ec1af5f8
Create Date: 2026-11-26 05:07:03.851370
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ba34931b5de5"
down_revision: str | None = "6900ec1af5f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_recipe_lines",
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("basis", sa.String(length=11), nullable=False),
        sa.CheckConstraint(
            "basis IN ('PER_PERSON', 'PER_SERVICE')",
            name=op.f("ck_inventory_recipe_lines_basis_valid"),
        ),
        sa.CheckConstraint(
            "quantity > 0", name=op.f("ck_inventory_recipe_lines_quantity_positive")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["inventory_products.id"],
            name=op.f("fk_inventory_recipe_lines_product_id"),
        ),
        sa.PrimaryKeyConstraint("service_id", "product_id", name=op.f("pk_inventory_recipe_lines")),
    )
    op.create_table(
        "inventory_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'CONSUMED', 'RELEASED')",
            name=op.f("ck_inventory_reservations_status_valid"),
        ),
        sa.CheckConstraint(
            "quantity > 0", name=op.f("ck_inventory_reservations_quantity_positive")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["inventory_products.id"],
            name=op.f("fk_inventory_reservations_product_id"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_reservations")),
    )
    op.create_index(
        op.f("ix_inventory_reservations_event_id"),
        "inventory_reservations",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_reservations_product_id"),
        "inventory_reservations",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        "uq_inventory_reservations_active",
        "inventory_reservations",
        ["event_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.add_column(
        "purchasing_purchases", sa.Column("expense_movement_id", sa.Uuid(), nullable=True)
    )
    op.create_unique_constraint(
        op.f("uq_purchasing_purchases_expense_movement_id"),
        "purchasing_purchases",
        ["expense_movement_id"],
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION purchasing_purchase_lock() RETURNS trigger AS $$
        BEGIN
            IF OLD.status IN ('RECEIVED', 'CANCELLED') THEN
                IF TG_OP = 'UPDATE' AND OLD.status = 'RECEIVED'
                   AND OLD.expense_movement_id IS NULL
                   AND NEW.expense_movement_id IS NOT NULL
                   AND (to_jsonb(NEW) - 'expense_movement_id')
                       = (to_jsonb(OLD) - 'expense_movement_id') THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'Una compra recibida o cancelada no se modifica';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION purchasing_purchase_lock() RETURNS trigger AS $$
        BEGIN
            IF OLD.status IN ('RECEIVED', 'CANCELLED') THEN
                RAISE EXCEPTION 'Una compra recibida o cancelada no se modifica';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.drop_constraint(
        op.f("uq_purchasing_purchases_expense_movement_id"), "purchasing_purchases", type_="unique"
    )
    op.drop_column("purchasing_purchases", "expense_movement_id")
    op.drop_index(
        "uq_inventory_reservations_active",
        table_name="inventory_reservations",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.drop_index(op.f("ix_inventory_reservations_product_id"), table_name="inventory_reservations")
    op.drop_index(op.f("ix_inventory_reservations_event_id"), table_name="inventory_reservations")
    op.drop_table("inventory_reservations")
    op.drop_table("inventory_recipe_lines")
