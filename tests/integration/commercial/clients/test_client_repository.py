"""Repositorio de clientes contra PostgreSQL real (HU04). Necesita Docker: `just test-all`.

Las tablas se crean con las migraciones de Alembic, igual que en producción.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.commercial.application.clients.errors import DuplicateDocumentError
from local_eventos.modules.commercial.domain.clients.client import (
    Client,
    Document,
    DocumentType,
)
from local_eventos.modules.commercial.domain.clients.document_correction import DocumentCorrection
from local_eventos.modules.commercial.infrastructure.client_repository import (
    SqlAlchemyClientRepository,
)
from local_eventos.modules.commercial.infrastructure.orm_models import DocumentCorrectionRow
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[4]


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
        await connection.execute(
            text(
                "TRUNCATE commercial_event_changes, commercial_event_activity_changes,"
                " commercial_event_activities,"
                " commercial_event_notes, commercial_event_services, commercial_events,"
                " commercial_event_counters,"
                " commercial_contracts, commercial_contract_counters,"
                " commercial_quote_lines, commercial_quotes,"
                " commercial_client_document_corrections, commercial_clients"
            )
        )
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _client(
    name: str = "José Ramírez Quispe", number: str = "44125896", phone: str = "987 654 321"
) -> Client:
    return Client.register(
        name=name,
        document_type=DocumentType.DNI,
        document_number=number,
        phone=phone,
        email="jose@correo.pe",
    )


async def test_hu04_guarda_y_lee_un_cliente(sessions: async_sessionmaker[AsyncSession]) -> None:
    client = _client()
    async with sessions.begin() as session:
        await SqlAlchemyClientRepository(session).add(client)

    async with sessions() as session:
        saved = await SqlAlchemyClientRepository(session).get(client.id)

    assert saved == client


async def test_hu04_busca_por_documento_exacto(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    client = _client()
    async with sessions.begin() as session:
        await SqlAlchemyClientRepository(session).add(client)

    async with sessions() as session:
        repository = SqlAlchemyClientRepository(session)
        found = await repository.get_by_document(Document(DocumentType.DNI, "44125896"))
        missing = await repository.get_by_document(Document(DocumentType.DNI, "11111111"))

    assert found is not None and found.id == client.id
    assert missing is None


async def test_hu04_la_base_de_datos_rechaza_documento_duplicado(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        await SqlAlchemyClientRepository(session).add(_client())

    with pytest.raises(DuplicateDocumentError):
        async with sessions.begin() as session:
            await SqlAlchemyClientRepository(session).add(_client(name="Otra persona"))


async def test_hu04_actualiza_un_cliente(sessions: async_sessionmaker[AsyncSession]) -> None:
    client = _client()
    async with sessions.begin() as session:
        await SqlAlchemyClientRepository(session).add(client)

    client.update_contact(name="José Ramírez", phone="912345678", address="SJL, Lima")
    client.deactivate()
    async with sessions.begin() as session:
        await SqlAlchemyClientRepository(session).update(client)

    async with sessions() as session:
        saved = await SqlAlchemyClientRepository(session).get(client.id)

    assert saved == client


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("jose ramirez", ["José Ramírez Quispe"]),
        ("RAMÍREZ", ["José Ramírez Quispe"]),
        ("4412", ["José Ramírez Quispe"]),
        ("987-654", ["José Ramírez Quispe"]),
        ("100%", []),
        ("", ["Colegio San Martín", "José Ramírez Quispe"]),
    ],
)
async def test_hu04_busca_por_nombre_sin_tildes_documento_o_telefono(
    sessions: async_sessionmaker[AsyncSession], text: str, expected: list[str]
) -> None:
    async with sessions.begin() as session:
        repository = SqlAlchemyClientRepository(session)
        await repository.add(_client())
        await repository.add(_client("Colegio San Martín", "20125478", phone="016543210"))

    async with sessions() as session:
        found = await SqlAlchemyClientRepository(session).search(
            text, include_inactive=False, limit=50
        )

    assert [c.name for c in found] == expected


async def test_hu04_busqueda_excluye_inactivos(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    client = _client()
    client.deactivate()
    async with sessions.begin() as session:
        await SqlAlchemyClientRepository(session).add(client)

    async with sessions() as session:
        repository = SqlAlchemyClientRepository(session)
        active_only = await repository.search("", include_inactive=False, limit=50)
        everyone = await repository.search("", include_inactive=True, limit=50)

    assert active_only == []
    assert [c.id for c in everyone] == [client.id]


async def test_rn03_si_falla_la_auditoria_no_se_guarda_la_correccion(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    client = _client()
    async with sessions.begin() as session:
        await SqlAlchemyClientRepository(session).add(client)

    previous = client.correct_document(
        document_type=DocumentType.DNI, document_number="44125869", reason="Error de digitación"
    )
    with pytest.raises(RuntimeError):
        async with sessions.begin() as session:
            repository = SqlAlchemyClientRepository(session)
            await repository.update(client)
            raise RuntimeError("falla antes de guardar la auditoría")

    async with sessions() as session:
        saved = await SqlAlchemyClientRepository(session).get(client.id)
    assert saved is not None and saved.document == previous


async def test_rn03_guarda_la_correccion_con_su_auditoria(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    client = _client()
    async with sessions.begin() as session:
        await SqlAlchemyClientRepository(session).add(client)

    previous = client.correct_document(
        document_type=DocumentType.DNI, document_number="44125869", reason="Error de digitación"
    )
    async with sessions.begin() as session:
        repository = SqlAlchemyClientRepository(session)
        await repository.update(client)
        await repository.add_document_correction(
            DocumentCorrection(
                client_id=client.id,
                previous=previous,
                new=client.document,
                reason="Error de digitación",
                corrected_by=uuid4(),
                corrected_at=datetime(2026, 11, 17, 15, 30, tzinfo=UTC),
            )
        )

    async with sessions() as session:
        audits = await session.scalar(select(func.count()).select_from(DocumentCorrectionRow))
        saved = await SqlAlchemyClientRepository(session).get(client.id)

    assert audits == 1
    assert saved is not None and saved.document.number == "44125869"
