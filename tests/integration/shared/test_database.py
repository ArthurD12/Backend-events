"""CA-3 y CA-4 con PostgreSQL real (Testcontainers). Necesita Docker: `just test-all`."""

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.community.postgres import PostgresContainer

from local_eventos.shared.infrastructure.db import check_database, create_engine

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as container:
        yield container


@pytest.fixture
async def engine(postgres: PostgresContainer) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(postgres.get_connection_url())
    yield engine
    await engine.dispose()


async def test_ca3_la_base_de_datos_responde(engine: AsyncEngine) -> None:
    await check_database(engine)


async def test_ca4_base_de_datos_inalcanzable_lanza_error() -> None:
    engine = create_engine("postgresql+asyncpg://nadie:nada@127.0.0.1:1/ninguna")

    with pytest.raises(OSError):
        await check_database(engine)
    await engine.dispose()
