"""Ensamblaje de dependencias del módulo identity.

Es el único lugar que conoce las clases concretas de `infrastructure`: el resto del módulo
trabaja con los puertos. El cifrador y el firmador se crean una sola vez por proceso.
"""

from functools import cache

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.identity.application.ports.access_log_repository import (
    AccessLogRepository,
)
from local_eventos.modules.identity.application.ports.security import (
    Clock,
    PasswordHasher,
    TokenIssuer,
)
from local_eventos.modules.identity.application.ports.session_repository import (
    SessionRepository,
)
from local_eventos.modules.identity.application.ports.user_repository import UserRepository
from local_eventos.modules.identity.infrastructure.access_log_repository import (
    SqlAlchemyAccessLogRepository,
)
from local_eventos.modules.identity.infrastructure.security import (
    Argon2PasswordHasher,
    AuthSettings,
    JwtTokenIssuer,
    SystemClock,
)
from local_eventos.modules.identity.infrastructure.session_repository import (
    SqlAlchemySessionRepository,
)
from local_eventos.modules.identity.infrastructure.user_repository import SqlAlchemyUserRepository


def user_repository(session: AsyncSession) -> UserRepository:
    return SqlAlchemyUserRepository(session)


def session_repository(session: AsyncSession) -> SessionRepository:
    return SqlAlchemySessionRepository(session)


def access_log_repository(session: AsyncSession) -> AccessLogRepository:
    return SqlAlchemyAccessLogRepository(session)


@cache
def password_hasher() -> PasswordHasher:
    return Argon2PasswordHasher()


@cache
def token_issuer() -> TokenIssuer:
    """Lee `JWT_SECRET` la primera vez que se necesita, no al importar."""
    return JwtTokenIssuer(AuthSettings().jwt_secret.get_secret_value())


def clock() -> Clock:
    return SystemClock()
