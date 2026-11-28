"""Migración de asistencia sobre una base vacía (HU18, T-07, plan §5.1/§5.2).

Aplica `upgrade head` sobre PostgreSQL limpio y comprueba las tablas, los CHECK
de estado y auditoría, el índice `(assignment_id, occurred_at)` y los dos
triggers; después revierte solo esta migración (`7c1f2a9d4e60`) y verifica que
tablas, constraints, índice y triggers desaparecen; por último vuelve a subir a
`head`. Necesita Docker.
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
_BEFORE_ATTENDANCE = "b959d55b8430"
_TABLES = {"staff_attendance", "staff_attendance_audit"}
_TRIGGERS = {
    "staff_attendance_no_delete",
    "staff_attendance_audit_append_only",
}
_CONSTRAINTS = {
    "pk_staff_attendance",
    "pk_staff_attendance_audit",
    "fk_staff_attendance_assignment_id",
    "fk_staff_attendance_audit_assignment_id",
    "ck_staff_attendance_status_valid",
    "ck_staff_attendance_audit_action_valid",
    "ck_staff_attendance_audit_previous_status_valid",
    "ck_staff_attendance_audit_new_status_valid",
    "ck_staff_attendance_audit_reason_and_status_valid",
}
_INDEX = "ix_staff_attendance_audit_assignment_occurred"


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
            constraints = set(
                (
                    await connection.execute(
                        text(
                            "SELECT c.conname FROM pg_constraint c"
                            " JOIN pg_class t ON t.oid = c.conrelid"
                            " JOIN pg_namespace n ON n.oid = t.relnamespace"
                            " WHERE n.nspname = 'public'"
                            " AND t.relname IN ('staff_attendance', 'staff_attendance_audit')"
                        )
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
            indexes = set(
                (
                    await connection.execute(
                        text("SELECT indexname FROM pg_indexes WHERE indexname = :name"),
                        {"name": _INDEX},
                    )
                ).scalars()
            )
    finally:
        await engine.dispose()
    return {
        "tables": tables,
        "constraints": constraints,
        "triggers": triggers,
        "indexes": indexes,
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
    assert applied["constraints"] == _CONSTRAINTS
    assert applied["triggers"] == _TRIGGERS
    assert applied["indexes"] == {_INDEX}

    command.downgrade(config, _BEFORE_ATTENDANCE)
    reverted = asyncio.run(_inspect(url))

    assert _TABLES.isdisjoint(reverted["tables"])
    assert reverted["triggers"] == set()
    assert _INDEX not in reverted["indexes"]

    command.upgrade(config, "head")
    again = asyncio.run(_inspect(url))

    assert again["tables"] >= _TABLES
    assert again["constraints"] == _CONSTRAINTS
    assert again["triggers"] == _TRIGGERS
    assert again["indexes"] == {_INDEX}
