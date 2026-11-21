"""Conexión a PostgreSQL con SQLAlchemy async."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_engine(database_url: str) -> AsyncEngine:
    """Crea el motor de conexiones. `pool_pre_ping` descarta conexiones caídas."""
    return create_async_engine(database_url, pool_pre_ping=True)


async def check_database(engine: AsyncEngine) -> None:
    """Lanza una excepción si la base de datos no responde."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
