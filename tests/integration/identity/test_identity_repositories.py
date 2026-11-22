"""Repositorios y seguridad de identidad contra PostgreSQL real (HU01–HU03).

Necesita Docker: `just test-all`. Las tablas se crean con las migraciones, igual que en producción.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.identity.application.errors import DuplicateEmailError
from local_eventos.modules.identity.application.ports.access_log_repository import (
    AccessLogFilter,
)
from local_eventos.modules.identity.domain.access_attempt import AccessAttempt, AccessResult
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.domain.session import Session
from local_eventos.modules.identity.domain.user import User
from local_eventos.modules.identity.infrastructure.access_log_repository import (
    SqlAlchemyAccessLogRepository,
)
from local_eventos.modules.identity.infrastructure.security import (
    Argon2PasswordHasher,
    JwtTokenIssuer,
)
from local_eventos.modules.identity.infrastructure.session_repository import (
    SqlAlchemySessionRepository,
)
from local_eventos.modules.identity.infrastructure.user_repository import SqlAlchemyUserRepository
from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 11, 22, 15, 0, tzinfo=UTC)


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
            text("TRUNCATE identity_access_log, identity_sessions, identity_users")
        )
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _user(email: str = "ana@darze.pe", role: Role = Role.ADMIN, name: str = "Ana Torres") -> User:
    return User.create(name=name, email=email, password_hash="hash", role=role)


async def _save(sessions: async_sessionmaker[AsyncSession], user: User) -> User:
    async with sessions.begin() as session:
        await SqlAlchemyUserRepository(session).add(user)
    return user


async def test_ca02_1_guarda_lee_y_actualiza_un_usuario(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    user = await _save(sessions, _user())
    user.update(name="Ana T.", email="ana.t@darze.pe", role=Role.EVENTS_MANAGER)
    user.deactivate()
    async with sessions.begin() as session:
        await SqlAlchemyUserRepository(session).update(user)

    async with sessions() as session:
        repository = SqlAlchemyUserRepository(session)
        assert await repository.get(user.id) == user
        assert await repository.get_by_email("ANA.T@darze.pe") == user
        assert await repository.list(include_inactive=False) == []
        assert await repository.list(include_inactive=True) == [user]


async def test_ca02_2_la_base_rechaza_correo_repetido_sin_importar_mayusculas(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _save(sessions, _user())
    other = _user()
    other.email = "ANA@DARZE.PE"  # saltándose la normalización a propósito

    with pytest.raises(DuplicateEmailError):
        await _save(sessions, other)


async def test_r_id_4_cuenta_solo_administradores_activos(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _save(sessions, _user("a1@darze.pe"))
    inactive = _user("a2@darze.pe")
    inactive.deactivate()
    await _save(sessions, inactive)
    await _save(sessions, _user("e@darze.pe", Role.EVENTS_MANAGER))

    async with sessions() as session:
        assert await SqlAlchemyUserRepository(session).count_active_admins() == 1


async def test_ca01_5_guarda_rota_y_revoca_sesiones(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    user = await _save(sessions, _user())
    first = Session.start(user_id=user.id, token_hash="a" * 64, now=NOW)
    second = Session.start(user_id=user.id, token_hash="b" * 64, now=NOW)
    async with sessions.begin() as session:
        repository = SqlAlchemySessionRepository(session)
        await repository.add(first)
        await repository.add(second)

    first.rotate(token_hash="c" * 64, now=NOW + timedelta(minutes=5))
    async with sessions.begin() as session:
        await SqlAlchemySessionRepository(session).update(first)
    async with sessions() as session:
        repository = SqlAlchemySessionRepository(session)
        assert await repository.get_by_token_hash("a" * 64) is None
        assert await repository.get_by_token_hash("c" * 64) == first

    async with sessions.begin() as session:
        await SqlAlchemySessionRepository(session).revoke_all_for_user(user.id, NOW)
    async with sessions() as session:
        repository = SqlAlchemySessionRepository(session)
        for token_hash in ("b" * 64, "c" * 64):
            saved = await repository.get_by_token_hash(token_hash)
            assert saved is not None and saved.revoked_at == NOW


async def test_ca03_1_y_ca03_3_registra_y_filtra_el_historial(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    ana = await _save(sessions, _user())
    async with sessions.begin() as session:
        repository = SqlAlchemyAccessLogRepository(session)
        for minutes, user_id, result in [
            (0, ana.id, AccessResult.SUCCESS),
            (10, None, AccessResult.INVALID_CREDENTIALS),
            (20, ana.id, AccessResult.INVALID_CREDENTIALS),
        ]:
            await repository.add(
                AccessAttempt(
                    email="ana@darze.pe" if user_id else "x@x.pe",
                    user_id=user_id,
                    result=result,
                    occurred_at=NOW + timedelta(minutes=minutes),
                )
            )

    async with sessions() as session:
        search = SqlAlchemyAccessLogRepository(session).search
        everything, total = await search(AccessLogFilter(), limit=2, offset=0)
        failed, failed_total = await search(
            AccessLogFilter(result=AccessResult.INVALID_CREDENTIALS), limit=50, offset=0
        )
        of_ana, _ = await search(
            AccessLogFilter(user_id=ana.id, since=NOW + timedelta(minutes=5)), limit=50, offset=0
        )

    assert total == 3 and len(everything) == 2
    assert everything[0].occurred_at == NOW + timedelta(minutes=20)
    assert everything[0].user_name == "Ana Torres"
    assert failed_total == 2
    assert [e.result for e in failed] == [AccessResult.INVALID_CREDENTIALS] * 2
    assert [e.occurred_at for e in of_ana] == [NOW + timedelta(minutes=20)]


@pytest.mark.parametrize(
    "statement",
    ["UPDATE identity_access_log SET result = 'SUCCESS'", "DELETE FROM identity_access_log"],
)
async def test_ca03_4_nadie_modifica_ni_borra_el_historial(
    sessions: async_sessionmaker[AsyncSession], statement: str
) -> None:
    async with sessions.begin() as session:
        await SqlAlchemyAccessLogRepository(session).add(
            AccessAttempt(
                email="x@x.pe",
                user_id=None,
                result=AccessResult.INVALID_CREDENTIALS,
                occurred_at=NOW,
            )
        )

    with pytest.raises(DBAPIError, match="no se puede modificar ni borrar"):
        async with sessions.begin() as session:
            await session.execute(text(statement))


def test_argon2_cifra_y_verifica_sin_guardar_la_clave() -> None:
    hasher = Argon2PasswordHasher()

    password_hash = hasher.hash("clave-segura")

    assert password_hash.startswith("$argon2")
    assert "clave-segura" not in password_hash
    assert hasher.verify("clave-segura", password_hash)
    assert not hasher.verify("otra-clave", password_hash)
    assert not hasher.verify("clave-segura", None)


def test_jwt_firma_y_rechaza_token_vencido_o_alterado() -> None:
    issuer = JwtTokenIssuer("s" * 32)
    user_id = uuid4()
    future = datetime.now(UTC) + timedelta(minutes=15)

    token = issuer.issue(user_id=user_id, role="ADMIN", expires_at=future)
    expired = issuer.issue(user_id=user_id, role="ADMIN", expires_at=datetime.now(UTC))

    claims = issuer.read(token)
    assert claims is not None and claims.user_id == user_id
    assert issuer.read(expired) is None
    assert issuer.read(token + "x") is None
    assert JwtTokenIssuer("o" * 32).read(token) is None
