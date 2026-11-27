"""Migración de asignaciones sobre una base vacía (HU17, T-17, plan §5.4).

Aplica `upgrade head` sobre PostgreSQL limpio y comprueba tablas, la extensión
`btree_gist`, la restricción de exclusión y los tres triggers; después revierte solo
esta migración (`6900ec1af5f8`) y verifica que las tablas y los triggers desaparecen
pero `btree_gist` permanece; por último vuelve a subir a `head`. Necesita Docker.
"""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer

from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_BEFORE_ASSIGNMENTS = "6900ec1af5f8"
_TABLES = {"staff_assignments", "staff_assignment_audit"}
_TRIGGERS = {
    "staff_assignment_audit_append_only",
    "staff_assignments_no_delete",
    "staff_assignments_immutable_keys",
}


@pytest.fixture(scope="module")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as container:
        yield container


async def _inspect(url: str) -> dict[str, set[str]]:
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            tables = set(
                (
                    await connection.execute(
                        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                    )
                ).scalars()
            )
            extensions = set(
                (await connection.execute(text("SELECT extname FROM pg_extension"))).scalars()
            )
            constraints = set(
                (
                    await connection.execute(
                        text("SELECT conname FROM pg_constraint WHERE conname = :name"),
                        {"name": "staff_assignments_no_overlap"},
                    )
                ).scalars()
            )
            triggers = set(
                (
                    await connection.execute(
                        text(
                            "SELECT tgname FROM pg_trigger"
                            " WHERE NOT tgisinternal AND tgname = ANY(:names)"
                        ),
                        {"names": sorted(_TRIGGERS)},
                    )
                ).scalars()
            )
    finally:
        await engine.dispose()
    return {
        "tables": tables,
        "extensions": extensions,
        "constraints": constraints,
        "triggers": triggers,
    }


def test_migracion_upgrade_downgrade_y_vuelta_a_head(
    postgres: PostgresContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = postgres.get_connection_url()
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(ROOT / "alembic.ini"))

    command.upgrade(config, "head")
    applied = asyncio.run(_inspect(url))

    assert applied["tables"] >= _TABLES
    assert "btree_gist" in applied["extensions"]
    assert applied["constraints"] == {"staff_assignments_no_overlap"}
    assert applied["triggers"] == _TRIGGERS

    command.downgrade(config, _BEFORE_ASSIGNMENTS)
    reverted = asyncio.run(_inspect(url))

    assert _TABLES.isdisjoint(reverted["tables"])
    assert reverted["triggers"] == set()
    assert reverted["constraints"] == set()
    # El `downgrade` no elimina la extensión: puede usarla otro esquema (ADR 0006).
    assert "btree_gist" in reverted["extensions"]

    command.upgrade(config, "head")
    again = asyncio.run(_inspect(url))

    assert again["tables"] >= _TABLES
    assert again["constraints"] == {"staff_assignments_no_overlap"}
    assert again["triggers"] == _TRIGGERS
