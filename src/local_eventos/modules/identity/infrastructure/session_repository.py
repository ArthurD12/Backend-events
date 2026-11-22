"""Repositorio de sesiones en PostgreSQL: implementa el puerto `SessionRepository` (HU01)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.identity.domain.session import Session
from local_eventos.modules.identity.infrastructure.orm_models import SessionRow


class SqlAlchemySessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: Session) -> None:
        row = SessionRow(id=session.id)
        _copy_to_row(session, row)
        self._session.add(row)
        await self._session.flush()

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        row = await self._session.scalar(
            select(SessionRow).where(SessionRow.token_hash == token_hash)
        )
        return _to_session(row) if row is not None else None

    async def update(self, session: Session) -> None:
        row = await self._session.get(SessionRow, session.id)
        if row is None:
            raise LookupError(f"La sesión {session.id} no existe en la base de datos.")
        _copy_to_row(session, row)
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: UUID, now: datetime) -> None:
        await self._session.execute(
            update(SessionRow)
            .where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
            .values(revoked_at=now)
            .execution_options(synchronize_session="fetch")
        )


def _to_session(row: SessionRow) -> Session:
    return Session(
        id=row.id,
        user_id=row.user_id,
        token_hash=row.token_hash,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
    )


def _copy_to_row(session: Session, row: SessionRow) -> None:
    row.user_id = session.user_id
    row.token_hash = session.token_hash
    row.created_at = session.created_at
    row.last_used_at = session.last_used_at
    row.expires_at = session.expires_at
    row.revoked_at = session.revoked_at
