"""Repositorios del catálogo contra PostgreSQL real (HU06). Necesita Docker: `just test-all`.

Las tablas se crean con las migraciones de Alembic, igual que en producción.
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.catalog.application.errors import DuplicateCategoryNameError
from local_eventos.modules.catalog.domain.category import Category
from local_eventos.modules.catalog.domain.service import PriceUnit, Service
from local_eventos.modules.catalog.infrastructure.category_repository import (
    SqlAlchemyCategoryRepository,
)
from local_eventos.modules.catalog.infrastructure.service_repository import (
    SqlAlchemyServiceRepository,
)
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("DATABASE_URL", url)
            command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        yield url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url)
    yield engine
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE catalog_services, catalog_categories"))
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _save_category(sessions: async_sessionmaker[AsyncSession], name: str) -> Category:
    category = Category.create(name=name)
    async with sessions.begin() as session:
        await SqlAlchemyCategoryRepository(session).add(category)
    return category


def _service(category_id: UUID, name: str = "Buffet criollo") -> Service:
    return Service.register(
        name=name,
        category_id=category_id,
        price_unit=PriceUnit.PER_PERSON,
        reference_price_cents=4500,
        description="Arroz con pollo, papa a la huancaína y chicha morada",
    )


async def test_hu06_guarda_y_lee_una_categoria(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    category = await _save_category(sessions, "Bebidas")

    async with sessions() as session:
        repository = SqlAlchemyCategoryRepository(session)
        assert await repository.get(category.id) == category
        assert await repository.get_by_name("BEBIDAS") == category
        assert await repository.get(uuid4()) is None


async def test_hu06_la_base_rechaza_nombres_repetidos_sin_importar_mayusculas(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _save_category(sessions, "Bebidas")

    with pytest.raises(DuplicateCategoryNameError):
        async with sessions.begin() as session:
            await SqlAlchemyCategoryRepository(session).add(Category.create(name="bebidas"))


async def test_hu06_actualiza_y_lista_categorias_ordenadas(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    mobiliario = await _save_category(sessions, "Mobiliario")
    await _save_category(sessions, "bebidas")
    animacion = await _save_category(sessions, "Animación")

    animacion.deactivate()
    mobiliario.rename(name="Mobiliario y menaje")
    async with sessions.begin() as session:
        repository = SqlAlchemyCategoryRepository(session)
        await repository.update(animacion)
        await repository.update(mobiliario)

    async with sessions() as session:
        repository = SqlAlchemyCategoryRepository(session)
        active = await repository.list(include_inactive=False)
        everything = await repository.list(include_inactive=True)

    assert [c.name for c in active] == ["bebidas", "Mobiliario y menaje"]
    assert [c.name for c in everything] == ["Animación", "bebidas", "Mobiliario y menaje"]


async def test_hu06_guarda_lee_y_actualiza_un_servicio(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    buffets = await _save_category(sessions, "Buffets")
    service = _service(buffets.id)
    async with sessions.begin() as session:
        await SqlAlchemyServiceRepository(session).add(service)

    service.update(
        name="Buffet criollo premium",
        category_id=buffets.id,
        price_unit=PriceUnit.PER_PERSON,
        reference_price_cents=5500,
    )
    async with sessions.begin() as session:
        await SqlAlchemyServiceRepository(session).update(service)

    async with sessions() as session:
        saved = await SqlAlchemyServiceRepository(session).get(service.id)
        currency = await session.scalar(
            text("SELECT currency FROM catalog_services WHERE id = :id"), {"id": service.id}
        )

    assert saved == service
    assert saved is not None and saved.description is None
    assert currency == "PEN"


async def test_hu06_sabe_si_una_categoria_tiene_servicios_activos(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    buffets = await _save_category(sessions, "Buffets")
    vacia = await _save_category(sessions, "Decoración")
    service = _service(buffets.id)
    async with sessions.begin() as session:
        await SqlAlchemyServiceRepository(session).add(service)

    async with sessions() as session:
        repository = SqlAlchemyServiceRepository(session)
        assert await repository.has_active_in_category(buffets.id) is True
        assert await repository.has_active_in_category(vacia.id) is False

    service.deactivate()
    async with sessions.begin() as session:
        await SqlAlchemyServiceRepository(session).update(service)

    async with sessions() as session:
        assert (
            await SqlAlchemyServiceRepository(session).has_active_in_category(buffets.id) is False
        )


async def test_hu06_busca_servicios_por_texto_categoria_y_estado(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    buffets = await _save_category(sessions, "Buffets")
    bebidas = await _save_category(sessions, "Bebidas")
    criollo = _service(buffets.id, "Buffet criollo")
    marino = _service(buffets.id, "buffet marino")
    chicha = _service(bebidas.id, "Chicha morada 100%")
    marino.deactivate()
    async with sessions.begin() as session:
        repository = SqlAlchemyServiceRepository(session)
        for service in (criollo, marino, chicha):
            await repository.add(service)

    async with sessions() as session:
        search = SqlAlchemyServiceRepository(session).search
        by_text = await search("BUFFET", category_id=None, active=None, limit=50)
        only_active = await search("", category_id=None, active=True, limit=50)
        by_category = await search("", category_id=bebidas.id, active=None, limit=50)
        percent = await search("%", category_id=None, active=None, limit=50)
        first = await search("", category_id=None, active=None, limit=1)

    assert [s.name for s in by_text] == ["Buffet criollo", "buffet marino"]
    assert [s.name for s in only_active] == ["Buffet criollo", "Chicha morada 100%"]
    assert [s.name for s in by_category] == ["Chicha morada 100%"]
    assert [s.name for s in percent] == ["Chicha morada 100%"]  # el % no es comodín
    assert [s.name for s in first] == ["Buffet criollo"]


async def test_hu06_la_base_rechaza_precio_negativo_y_categoria_inexistente(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    buffets = await _save_category(sessions, "Buffets")
    negativo = _service(buffets.id)
    negativo.reference_price_cents = -1  # saltándose el dominio a propósito
    sin_categoria = _service(uuid4())

    for service in (negativo, sin_categoria):
        with pytest.raises(IntegrityError):
            async with sessions.begin() as session:
                await SqlAlchemyServiceRepository(session).add(service)
