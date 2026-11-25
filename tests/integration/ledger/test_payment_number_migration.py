"""La migración de pagos parciales numera los pagos que ya existían (CA-20.1). Necesita Docker."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer

from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
BEFORE = "a4f88017b782"  # la migración anterior a la de pagos


@pytest.fixture(scope="module")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as container:
        yield container


def test_los_pagos_existentes_reciben_numero_por_anio_y_orden(
    postgres: PostgresContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = postgres.get_connection_url()
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, BEFORE)
    rows = [
        # 31/12/2025 23:30 en Lima ya es 2026 en UTC: cuenta para 2025.
        ("00000000-0000-0000-0000-000000000001", datetime(2026, 1, 1, 4, 30, tzinfo=UTC)),
        ("00000000-0000-0000-0000-000000000002", datetime(2026, 3, 1, 15, tzinfo=UTC)),
        ("00000000-0000-0000-0000-000000000003", datetime(2026, 2, 1, 15, tzinfo=UTC)),
    ]
    insert = (
        "INSERT INTO ledger_payments (id, contract_id, kind, amount_cents, method, paid_on,"
        " recorded_by, recorded_at) VALUES (CAST(:id AS uuid), gen_random_uuid(), 'ADVANCE',"
        " 100, 'CASH', DATE '2025-12-31', gen_random_uuid(), :at)"
    )
    asyncio.run(_run(url, [(insert, {"id": i, "at": at}) for i, at in rows]))

    command.upgrade(config, "head")

    numbers, counters = asyncio.run(
        _run(
            url,
            [
                ("SELECT id::text, number FROM ledger_payments ORDER BY id", {}),
                ("SELECT year, last FROM ledger_payment_counters ORDER BY year", {}),
            ],
        )
    )
    assert [n for _, n in numbers] == ["PAG-2025-0001", "PAG-2026-0002", "PAG-2026-0001"]
    assert [tuple(c) for c in counters] == [(2025, 1), (2026, 2)]


async def _run(url: str, statements: list[tuple[str, dict[str, Any]]]) -> list[list[Any]]:
    engine = create_engine(url)
    try:
        async with engine.begin() as connection:
            results = []
            for sql, params in statements:
                result = await connection.execute(text(sql), params)
                results.append(list(result.all()) if result.returns_rows else [])
            return results
    finally:
        await engine.dispose()
