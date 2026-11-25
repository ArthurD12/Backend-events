"""Dependencias de FastAPI del módulo inventory. En las pruebas se reemplazan por piezas en memoria.

Todos los repositorios usan la misma sesión de la petición: el movimiento y el stock nuevo se
confirman o se deshacen juntos.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial.public_api import EventLookup
from local_eventos.modules.inventory import composition
from local_eventos.modules.inventory.application.ports.clock import Clock
from local_eventos.modules.inventory.application.ports.product_repository import (
    ProductRepository,
)
from local_eventos.modules.inventory.application.ports.stock_repository import (
    MovementRepository,
    StockRepository,
)
from local_eventos.shared.presentation.database import get_session

Session = Annotated[AsyncSession, Depends(get_session)]


async def get_product_repository(session: Session) -> ProductRepository:
    return composition.product_repository(session)


async def get_stock_repository(session: Session) -> StockRepository:
    return composition.stock_repository(session)


async def get_movement_repository(session: Session) -> MovementRepository:
    return composition.movement_repository(session)


async def get_event_lookup(session: Session) -> EventLookup:
    return composition.events(session)


def get_clock() -> Clock:
    return composition.clock()


Products = Annotated[ProductRepository, Depends(get_product_repository)]
Stock = Annotated[StockRepository, Depends(get_stock_repository)]
Movements = Annotated[MovementRepository, Depends(get_movement_repository)]
Events = Annotated[EventLookup, Depends(get_event_lookup)]
Today = Annotated[Clock, Depends(get_clock)]
