"""unir personal (HU15) con eventos, pagos e inventario

Revision ID: 6900ec1af5f8
Revises: f3f48810ccb5, 652825952ff5
Create Date: 2026-11-25 17:42:25.608775

Migración de unión, sin cambios de esquema. Personal (HU15) y la línea de eventos, pagos
e inventario salieron del mismo punto (d0f713f5dc65) y quedaron dos heads. Ninguna
migración existente se edita (AGENTS.md, regla 8).
"""

from collections.abc import Sequence

revision: str = "6900ec1af5f8"
down_revision: str | Sequence[str] | None = ("f3f48810ccb5", "652825952ff5")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
