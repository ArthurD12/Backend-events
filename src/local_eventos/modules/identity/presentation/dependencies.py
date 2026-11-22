"""Dependencias de FastAPI del módulo identity: repositorios, seguridad y usuario actual.

`require_permission` es lo que usan los demás módulos (vía `identity.public_api`) para
proteger sus rutas: sin sesión responde 401; sin el permiso del rol, 403 (CA-01.7).
En las pruebas se reemplazan por piezas en memoria.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.identity import composition
from local_eventos.modules.identity.application.errors import (
    ForbiddenError,
    NotAuthenticatedError,
)
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
from local_eventos.modules.identity.application.use_cases.authentication import (
    AuthenticateAccessToken,
)
from local_eventos.modules.identity.domain.permissions import Permission, Role
from local_eventos.shared.presentation.database import get_session

_bearer = HTTPBearer(auto_error=False, description="Access token de `POST /v1/auth/login`")


async def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRepository:
    return composition.user_repository(session)


async def get_session_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SessionRepository:
    return composition.session_repository(session)


async def get_access_log_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccessLogRepository:
    return composition.access_log_repository(session)


def get_password_hasher() -> PasswordHasher:
    return composition.password_hasher()


def get_token_issuer() -> TokenIssuer:
    return composition.token_issuer()


def get_clock() -> Clock:
    return composition.clock()


Users = Annotated[UserRepository, Depends(get_user_repository)]
Sessions = Annotated[SessionRepository, Depends(get_session_repository)]
AccessLog = Annotated[AccessLogRepository, Depends(get_access_log_repository)]
Hasher = Annotated[PasswordHasher, Depends(get_password_hasher)]
Tokens = Annotated[TokenIssuer, Depends(get_token_issuer)]
Now = Annotated[Clock, Depends(get_clock)]


@dataclass(frozen=True)
class CurrentUser:
    """Quién hace la petición. Los módulos lo usarán para auditar (RN03: usuario y fecha)."""

    id: UUID
    name: str
    role: Role
    permissions: frozenset[Permission]


async def _access_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Sin token responde 401 de inmediato, sin abrir una conexión a la base de datos."""
    if credentials is None:
        raise NotAuthenticatedError()
    return credentials.credentials


async def get_current_user(
    token: Annotated[str, Depends(_access_token)],
    users: Users,
    tokens: Tokens,
) -> CurrentUser:
    user = await AuthenticateAccessToken(users, tokens)(token)
    return CurrentUser(id=user.id, name=user.name, role=user.role, permissions=user.permissions)


def require_permission(permission: Permission) -> Callable[..., Awaitable[CurrentUser]]:
    """Dependencia que exige sesión y el permiso indicado: `Depends(require_permission(...))`."""

    async def check(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if permission not in user.permissions:
            raise ForbiddenError()
        return user

    return check
