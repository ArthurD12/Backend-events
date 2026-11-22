"""Casos de uso de sesión: iniciar, renovar y cerrar sesión, y quién soy (HU01, HU03).

El access token (JWT) dura 15 minutos y va en cada petición. El refresh token renueva el acceso
y se vence tras 30 minutos sin uso: así la sesión termina por inactividad (CA-01.6).
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from local_eventos.modules.identity.application.errors import (
    NotAuthenticatedError,
    SessionExpiredError,
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
from local_eventos.modules.identity.domain.access_attempt import AccessAttempt, AccessResult
from local_eventos.modules.identity.domain.errors import UserValidationError
from local_eventos.modules.identity.domain.session import Session
from local_eventos.modules.identity.domain.user import User, normalize_email

ACCESS_TOKEN_TTL = timedelta(minutes=15)
_MAX_LOGGED_EMAIL = 254


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    user: User


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Login:
    """Valida las credenciales y registra el intento en el historial, salga bien o mal.

    Si se rechaza devuelve `None` (no lanza error): así la transacción se confirma y el intento
    fallido queda guardado (CA-03.1). El mensaje no dice si falló el correo, la clave o el
    estado de la cuenta (CA-01.2); el historial sí guarda el motivo real.
    """

    def __init__(
        self,
        users: UserRepository,
        sessions: SessionRepository,
        access_log: AccessLogRepository,
        hasher: PasswordHasher,
        tokens: TokenIssuer,
        clock: Clock,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._access_log = access_log
        self._hasher = hasher
        self._tokens = tokens
        self._clock = clock

    async def __call__(self, email: str, password: str) -> IssuedTokens | None:
        now = self._clock.now()
        logged_email = email.strip().lower()[:_MAX_LOGGED_EMAIL]
        try:
            user = await self._users.get_by_email(normalize_email(email))
        except UserValidationError:
            user = None

        if not self._hasher.verify(password, user.password_hash if user else None):
            await self._record(logged_email, user, AccessResult.INVALID_CREDENTIALS, now)
            return None
        assert user is not None
        if not user.active:
            await self._record(logged_email, user, AccessResult.INACTIVE_USER, now)
            return None

        await self._record(logged_email, user, AccessResult.SUCCESS, now)
        refresh_token = secrets.token_urlsafe(32)
        await self._sessions.add(
            Session.start(user_id=user.id, token_hash=hash_refresh_token(refresh_token), now=now)
        )
        return _issue(self._tokens, user, refresh_token, now)

    async def _record(
        self, email: str, user: User | None, result: AccessResult, now: datetime
    ) -> None:
        await self._access_log.add(
            AccessAttempt(
                email=email, user_id=user.id if user else None, result=result, occurred_at=now
            )
        )


class RefreshSession:
    """Entrega un access token nuevo y rota el refresh token (el anterior deja de servir)."""

    def __init__(
        self,
        users: UserRepository,
        sessions: SessionRepository,
        tokens: TokenIssuer,
        clock: Clock,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._tokens = tokens
        self._clock = clock

    async def __call__(self, refresh_token: str) -> IssuedTokens:
        now = self._clock.now()
        session = await self._sessions.get_by_token_hash(hash_refresh_token(refresh_token))
        if session is None or not session.is_usable(now):
            raise SessionExpiredError()
        user = await self._users.get(session.user_id)
        if user is None or not user.active:
            raise SessionExpiredError()
        new_token = secrets.token_urlsafe(32)
        session.rotate(token_hash=hash_refresh_token(new_token), now=now)
        await self._sessions.update(session)
        return _issue(self._tokens, user, new_token, now)


class Logout:
    """Cierra la sesión. Si el token ya no existe no pasa nada: cerrar dos veces no es error."""

    def __init__(self, sessions: SessionRepository, clock: Clock) -> None:
        self._sessions = sessions
        self._clock = clock

    async def __call__(self, refresh_token: str) -> None:
        session = await self._sessions.get_by_token_hash(hash_refresh_token(refresh_token))
        if session is not None:
            session.revoke(self._clock.now())
            await self._sessions.update(session)


class AuthenticateAccessToken:
    """Identifica al usuario de una petición. Lee la base: un usuario desactivado o con otro
    rol pierde el acceso al instante, sin esperar a que venza su token (CA-02.4)."""

    def __init__(self, users: UserRepository, tokens: TokenIssuer) -> None:
        self._users = users
        self._tokens = tokens

    async def __call__(self, access_token: str | None) -> User:
        if not access_token:
            raise NotAuthenticatedError()
        claims = self._tokens.read(access_token)
        if claims is None:
            raise SessionExpiredError()
        user = await self._users.get(claims.user_id)
        if user is None or not user.active:
            raise SessionExpiredError()
        return user


def _issue(tokens: TokenIssuer, user: User, refresh_token: str, now: datetime) -> IssuedTokens:
    expires_at = now + ACCESS_TOKEN_TTL
    return IssuedTokens(
        access_token=tokens.issue(user_id=user.id, role=user.role.value, expires_at=expires_at),
        access_expires_at=expires_at,
        refresh_token=refresh_token,
        user=user,
    )
