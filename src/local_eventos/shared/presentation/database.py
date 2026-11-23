"""Una sesión de base de datos por petición HTTP, con su transacción.

Si la petición termina bien, se confirma (commit); si algo falla, se deshace (rollback).
Así, un caso de uso que guarda dos cosas (p. ej. el cliente y su auditoría) las guarda juntas.
"""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessions: async_sessionmaker[AsyncSession] = request.app.state.sessions
    async with sessions.begin() as session:
        yield session
