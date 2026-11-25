"""Dependencias de FastAPI de purchasing. En las pruebas se reemplazan por piezas en memoria.

Todas usan la misma sesión de la petición: recibir una compra y registrar sus entradas de
almacén se confirma o se deshace junto.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.inventory.public_api import LowStockLookup, ProductLookup, StockReceiver
from local_eventos.modules.purchasing import composition
from local_eventos.modules.purchasing.application.ports.clock import Clock
from local_eventos.modules.purchasing.application.ports.repositories import (
    PurchaseRepository,
    SupplierRepository,
)
from local_eventos.shared.presentation.database import get_session

Session = Annotated[AsyncSession, Depends(get_session)]


async def get_supplier_repository(session: Session) -> SupplierRepository:
    return composition.supplier_repository(session)


async def get_purchase_repository(session: Session) -> PurchaseRepository:
    return composition.purchase_repository(session)


async def get_product_lookup(session: Session) -> ProductLookup:
    return composition.products(session)


async def get_low_stock_lookup(session: Session) -> LowStockLookup:
    return composition.low_stock(session)


async def get_stock_receiver(session: Session) -> StockReceiver:
    return composition.receiver(session)


def get_clock() -> Clock:
    return composition.clock()


Suppliers = Annotated[SupplierRepository, Depends(get_supplier_repository)]
Purchases = Annotated[PurchaseRepository, Depends(get_purchase_repository)]
Products = Annotated[ProductLookup, Depends(get_product_lookup)]
LowStock = Annotated[LowStockLookup, Depends(get_low_stock_lookup)]
Receiver = Annotated[StockReceiver, Depends(get_stock_receiver)]
Today = Annotated[Clock, Depends(get_clock)]
