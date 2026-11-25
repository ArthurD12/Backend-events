"""Puertos del stock y de los movimientos. Los movimientos solo se agregan y se leen."""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.inventory.domain.movement import Movement
from local_eventos.modules.inventory.domain.stock import StockLevel


class StockRepository(Protocol):
    async def lock(self, product_id: UUID) -> StockLevel:
        """Stock del producto, bloqueado hasta el fin de la transacción (`SELECT … FOR UPDATE`).

        Dos movimientos del mismo producto se registran uno después del otro.
        """
        ...

    async def save(self, level: StockLevel) -> None: ...

    async def get_many(self, product_ids: list[UUID]) -> dict[UUID, StockLevel]:
        """Stock de cada producto; los que no tienen movimientos no aparecen."""
        ...


class MovementRepository(Protocol):
    async def add(self, movement: Movement) -> None: ...

    async def list_for_product(
        self, product_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Movement], int]:
        """Una página, del más reciente al más antiguo, y el total."""
        ...

    async def list_for_event(
        self, event_id: UUID, product_id: UUID | None = None
    ) -> list[Movement]:
        """Movimientos del evento (o de un producto en él), del más antiguo al más reciente."""
        ...

    async def entries_for(self, product_ids: list[UUID]) -> list[Movement]:
        """Entradas de esos productos (para las alertas de vencimiento)."""
        ...
