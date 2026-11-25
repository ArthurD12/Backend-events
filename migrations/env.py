"""Entorno de Alembic en modo async (asyncpg).

`just migrate` aplica las migraciones pendientes; `just migration "<nombre>"` genera una nueva
comparando los modelos ORM (`Base.metadata`) con la base de datos.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Cada módulo con tablas se importa aquí para que Alembic las vea al generar migraciones.
from local_eventos.modules.catalog.infrastructure import orm_models as catalog_orm  # noqa: F401
from local_eventos.modules.commercial.infrastructure import orm_models  # noqa: F401
from local_eventos.modules.identity.infrastructure import orm_models as identity_orm  # noqa: F401
from local_eventos.modules.inventory.infrastructure import orm_models as inventory_orm  # noqa: F401
from local_eventos.modules.ledger.infrastructure import orm_models as ledger_orm  # noqa: F401
from local_eventos.modules.purchasing.infrastructure import orm_models as purchasing_orm  # noqa: F401
from local_eventos.shared.infrastructure.config import Settings
from local_eventos.shared.infrastructure.orm import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return Settings().database_url


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse (`alembic upgrade head --sql`)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_database_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
