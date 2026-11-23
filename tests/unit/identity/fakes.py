"""Piezas falsas de identidad para probar los casos de uso sin base de datos."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from local_eventos.modules.identity.application.ports.access_log_repository import (
    AccessLogEntry,
    AccessLogFilter,
)
from local_eventos.modules.identity.application.ports.security import AccessTokenClaims
from local_eventos.modules.identity.domain.access_attempt import AccessAttempt
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.domain.session import Session
from local_eventos.modules.identity.domain.user import User


class InMemoryUserRepository:
    """Guarda copias: así un cambio sin `update` no se "filtra" al repositorio."""

    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}

    async def get(self, user_id: UUID) -> User | None:
        user = self.users.get(user_id)
        return replace(user) if user else None

    async def get_by_email(self, email: str) -> User | None:
        return next((replace(u) for u in self.users.values() if u.email == email), None)

    async def add(self, user: User) -> None:
        self.users[user.id] = replace(user)

    async def update(self, user: User) -> None:
        self.users[user.id] = replace(user)

    async def list(self, *, include_inactive: bool) -> list[User]:
        found = [replace(u) for u in self.users.values() if include_inactive or u.active]
        return sorted(found, key=lambda u: u.name.lower())

    async def count_active_admins(self) -> int:
        return sum(1 for u in self.users.values() if u.active and u.role is Role.ADMIN)


class InMemorySessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[UUID, Session] = {}

    async def add(self, session: Session) -> None:
        self.sessions[session.id] = replace(session)

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        return next(
            (replace(s) for s in self.sessions.values() if s.token_hash == token_hash), None
        )

    async def update(self, session: Session) -> None:
        self.sessions[session.id] = replace(session)

    async def revoke_all_for_user(self, user_id: UUID, now: datetime) -> None:
        for session in self.sessions.values():
            if session.user_id == user_id:
                session.revoke(now)


class InMemoryAccessLogRepository:
    def __init__(self, users: InMemoryUserRepository | None = None) -> None:
        self.attempts: list[AccessAttempt] = []
        self._users = users

    async def add(self, attempt: AccessAttempt) -> None:
        self.attempts.append(attempt)

    async def search(
        self, filters: AccessLogFilter, *, limit: int, offset: int
    ) -> tuple[list[AccessLogEntry], int]:
        found = [
            AccessLogEntry(
                id=number,
                email=a.email,
                user_id=a.user_id,
                user_name=self._name(a.user_id),
                result=a.result,
                occurred_at=a.occurred_at,
            )
            for number, a in enumerate(self.attempts, start=1)
            if (filters.user_id is None or a.user_id == filters.user_id)
            and (filters.result is None or a.result == filters.result)
            and (filters.since is None or a.occurred_at >= filters.since)
            and (filters.until is None or a.occurred_at <= filters.until)
        ]
        found.sort(key=lambda e: (e.occurred_at, e.id), reverse=True)
        return found[offset : offset + limit], len(found)

    def _name(self, user_id: UUID | None) -> str | None:
        if user_id is None or self._users is None or user_id not in self._users.users:
            return None
        return self._users.users[user_id].name


class FakePasswordHasher:
    """Simula el cifrado: el "hash" es la clave con un prefijo. Nunca usar fuera de pruebas."""

    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, password_hash: str | None) -> bool:
        return password_hash is not None and password_hash == f"hashed:{password}"


class FakeTokenIssuer:
    """Token legible para pruebas: `token:<id>:<vence>`. Verifica el vencimiento con el reloj."""

    def __init__(self, clock: "FakeClock") -> None:
        self._clock = clock

    def issue(self, *, user_id: UUID, role: str, expires_at: datetime) -> str:
        return f"token:{user_id}:{expires_at.isoformat()}"

    def read(self, token: str) -> AccessTokenClaims | None:
        try:
            prefix, user_id, expires_at = token.split(":", 2)
            if prefix != "token" or datetime.fromisoformat(expires_at) <= self._clock.now():
                return None
            return AccessTokenClaims(user_id=UUID(user_id))
        except ValueError:
            return None


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 11, 22, 15, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> None:
        self.current += timedelta(**delta)
