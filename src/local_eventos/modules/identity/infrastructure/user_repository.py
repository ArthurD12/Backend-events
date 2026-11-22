"""Repositorio de usuarios en PostgreSQL: implementa el puerto `UserRepository` (HU02).

No confirma la transacción: eso lo decide quien abre la sesión, una vez por petición.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.identity.application.errors import DuplicateEmailError
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.domain.user import User
from local_eventos.modules.identity.infrastructure.orm_models import UserRow


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> User | None:
        row = await self._session.get(UserRow, user_id)
        return _to_user(row) if row is not None else None

    async def get_by_email(self, email: str) -> User | None:
        row = await self._session.scalar(
            select(UserRow).where(func.lower(UserRow.email) == email.lower())
        )
        return _to_user(row) if row is not None else None

    async def add(self, user: User) -> None:
        row = UserRow(id=user.id)
        _copy_to_row(user, row)
        self._session.add(row)
        await self._flush()

    async def update(self, user: User) -> None:
        row = await self._session.get(UserRow, user.id)
        if row is None:
            raise LookupError(f"El usuario {user.id} no existe en la base de datos.")
        _copy_to_row(user, row)
        await self._flush()

    async def list(self, *, include_inactive: bool) -> list[User]:
        query = select(UserRow)
        if not include_inactive:
            query = query.where(UserRow.active.is_(True))
        rows = await self._session.scalars(query.order_by(func.lower(UserRow.name)))
        return [_to_user(row) for row in rows]

    async def count_active_admins(self) -> int:
        query = select(func.count()).where(
            UserRow.active.is_(True), UserRow.role == Role.ADMIN.value
        )
        return int(await self._session.scalar(query) or 0)

    async def _flush(self) -> None:
        """Si dos personas registran el mismo correo a la vez, el índice único gana."""
        try:
            await self._session.flush()
        except IntegrityError as error:
            if "uq_identity_users_email_lower" in str(error.orig):
                raise DuplicateEmailError() from error
            raise


def _to_user(row: UserRow) -> User:
    return User(
        id=row.id,
        name=row.name,
        email=row.email,
        password_hash=row.password_hash,
        role=Role(row.role),
        active=row.active,
    )


def _copy_to_row(user: User, row: UserRow) -> None:
    row.name = user.name
    row.email = user.email
    row.password_hash = user.password_hash
    row.role = user.role.value
    row.active = user.active
