"""Las migraciones se aplican y se revierten sobre una base vacía. Necesita Docker."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as container:
        yield container


def test_migraciones_suben_y_bajan_en_una_base_vacia(
    postgres: PostgresContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres.get_connection_url())
    config = Config(str(ROOT / "alembic.ini"))

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
