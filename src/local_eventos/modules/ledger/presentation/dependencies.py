"""Dependencias de FastAPI del módulo ledger. En las pruebas se reemplazan por fakes."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.identity.public_api import UserNamesLookup, user_names
from local_eventos.modules.ledger import composition
from local_eventos.modules.ledger.application.ports.clock import Clock
from local_eventos.modules.ledger.application.ports.movement_repository import MovementRepository
from local_eventos.shared.presentation.database import get_session


async def get_movement_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MovementRepository:
    return composition.movement_repository(session)


def get_clock() -> Clock:
    return composition.clock()


async def get_user_names(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserNamesLookup:
    """Quién registró o anuló cada movimiento, por la `public_api` de identity."""
    return user_names(session)


Movements = Annotated[MovementRepository, Depends(get_movement_repository)]
Today = Annotated[Clock, Depends(get_clock)]
UserNames = Annotated[UserNamesLookup, Depends(get_user_names)]
