"""Casos de uso de gestión de usuarios (HU02). Solo los usa el administrador.

Nunca se elimina un usuario: se desactiva (RN02). Nunca se deja al sistema sin un
administrador activo (R-ID-4).
"""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.identity.application.errors import (
    DuplicateEmailError,
    LastAdminError,
    UserNotFoundError,
)
from local_eventos.modules.identity.application.ports.security import Clock, PasswordHasher
from local_eventos.modules.identity.application.ports.session_repository import (
    SessionRepository,
)
from local_eventos.modules.identity.application.ports.user_repository import UserRepository
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.domain.user import (
    User,
    check_password_policy,
    normalize_email,
)


@dataclass(frozen=True)
class CreateUserCommand:
    name: str
    email: str
    password: str
    role: Role
    active: bool = True


@dataclass(frozen=True)
class UpdateUserCommand:
    user_id: UUID
    name: str
    email: str
    role: Role
    new_password: str | None = None


class CreateUser:
    def __init__(self, users: UserRepository, hasher: PasswordHasher) -> None:
        self._users = users
        self._hasher = hasher

    async def __call__(self, command: CreateUserCommand) -> User:
        check_password_policy(command.password)
        user = User.create(
            name=command.name,
            email=command.email,
            password_hash="",
            role=command.role,
            active=command.active,
        )
        if await self._users.get_by_email(user.email) is not None:
            raise DuplicateEmailError()
        user.set_password_hash(self._hasher.hash(command.password))
        await self._users.add(user)
        return user


class UpdateUser:
    """Cambia datos, rol y, si se envía, la contraseña. Con clave nueva se cierran sus sesiones."""

    def __init__(
        self,
        users: UserRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        clock: Clock,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._hasher = hasher
        self._clock = clock

    async def __call__(self, command: UpdateUserCommand) -> User:
        user = await _get_or_fail(self._users, command.user_id)
        if command.new_password is not None:
            check_password_policy(command.new_password)
        if user.is_active_admin and command.role is not Role.ADMIN:
            await _ensure_another_admin(self._users)
        other = await self._users.get_by_email(normalize_email(command.email))
        if other is not None and other.id != user.id:
            raise DuplicateEmailError()
        user.update(name=command.name, email=command.email, role=command.role)
        if command.new_password is not None:
            user.set_password_hash(self._hasher.hash(command.new_password))
            await self._sessions.revoke_all_for_user(user.id, self._clock.now())
        await self._users.update(user)
        return user


class DeactivateUser:
    """Desactiva y cierra todas sus sesiones: deja de entrar al instante (CA-02.4)."""

    def __init__(self, users: UserRepository, sessions: SessionRepository, clock: Clock) -> None:
        self._users = users
        self._sessions = sessions
        self._clock = clock

    async def __call__(self, user_id: UUID) -> User:
        user = await _get_or_fail(self._users, user_id)
        if user.is_active_admin:
            await _ensure_another_admin(self._users)
        user.deactivate()
        await self._users.update(user)
        await self._sessions.revoke_all_for_user(user.id, self._clock.now())
        return user


class ActivateUser:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def __call__(self, user_id: UUID) -> User:
        user = await _get_or_fail(self._users, user_id)
        user.activate()
        await self._users.update(user)
        return user


class GetUser:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def __call__(self, user_id: UUID) -> User:
        return await _get_or_fail(self._users, user_id)


class ListUsers:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def __call__(self, *, include_inactive: bool = False) -> list[User]:
        return await self._users.list(include_inactive=include_inactive)


async def _get_or_fail(users: UserRepository, user_id: UUID) -> User:
    user = await users.get(user_id)
    if user is None:
        raise UserNotFoundError()
    return user


async def _ensure_another_admin(users: UserRepository) -> None:
    if await users.count_active_admins() <= 1:
        raise LastAdminError()
