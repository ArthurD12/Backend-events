"""Stock y movimientos en PostgreSQL.

Los movimientos solo se insertan y se leen (AGENTS.md, regla 5). El stock se bloquea con
`SELECT … FOR UPDATE` antes de cada movimiento: dos salidas simultáneas del mismo producto se
registran una tras otra y la segunda ve el stock ya descontado (RN20).
"""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.inventory.domain.movement import Movement, MovementKind
from local_eventos.modules.inventory.domain.quantity import ZERO
from local_eventos.modules.inventory.domain.stock import StockLevel
from local_eventos.modules.inventory.infrastructure.orm_models import MovementRow, StockRow


class SqlAlchemyStockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock(self, product_id: UUID) -> StockLevel:
        await self._session.execute(
            insert(StockRow)
            .values(product_id=product_id, quantity=ZERO, avg_cost_cents=0)
            .on_conflict_do_nothing(index_elements=[StockRow.product_id])
        )
        row = await self._session.scalar(
            select(StockRow)
            .where(StockRow.product_id == product_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert row is not None
        return StockLevel(row.product_id, row.quantity, row.avg_cost_cents)

    async def save(self, level: StockLevel) -> None:
        row = await self._session.get(StockRow, level.product_id)
        if row is None:
            raise LookupError("Bloquea el stock (`lock`) antes de guardarlo.")
        row.quantity = level.quantity
        row.avg_cost_cents = level.avg_cost_cents
        await self._session.flush()

    async def get_many(self, product_ids: list[UUID]) -> dict[UUID, StockLevel]:
        if not product_ids:
            return {}
        rows = await self._session.scalars(
            select(StockRow).where(StockRow.product_id.in_(product_ids))
        )
        return {r.product_id: StockLevel(r.product_id, r.quantity, r.avg_cost_cents) for r in rows}


class SqlAlchemyMovementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, movement: Movement) -> None:
        self._session.add(
            MovementRow(
                id=movement.id,
                product_id=movement.product_id,
                kind=movement.kind.value,
                quantity=movement.quantity,
                occurred_on=movement.occurred_on,
                event_id=movement.event_id,
                unit_cost_cents=movement.unit_cost_cents,
                supplier_id=movement.supplier_id,
                lot=movement.lot,
                expires_on=movement.expires_on,
                reason=movement.reason,
                purchase_id=movement.purchase_id,
                recorded_by=movement.recorded_by,
                recorded_at=movement.recorded_at,
            )
        )
        await self._session.flush()

    async def list_for_product(
        self, product_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Movement], int]:
        condition = MovementRow.product_id == product_id
        total = await self._session.scalar(select(func.count()).where(condition))
        rows = await self._session.scalars(
            select(MovementRow)
            .where(condition)
            .order_by(MovementRow.recorded_at.desc(), MovementRow.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_to_movement(row) for row in rows], int(total or 0)

    async def list_for_event(
        self, event_id: UUID, product_id: UUID | None = None
    ) -> list[Movement]:
        query = select(MovementRow).where(MovementRow.event_id == event_id)
        if product_id is not None:
            query = query.where(MovementRow.product_id == product_id)
        rows = await self._session.scalars(query.order_by(MovementRow.recorded_at, MovementRow.id))
        return [_to_movement(row) for row in rows]

    async def entries_for(self, product_ids: list[UUID]) -> list[Movement]:
        if not product_ids:
            return []
        rows = await self._session.scalars(
            select(MovementRow).where(
                MovementRow.product_id.in_(product_ids),
                MovementRow.kind == MovementKind.ENTRY.value,
            )
        )
        return [_to_movement(row) for row in rows]

    async def list_between(
        self, date_from: date, date_to: date, kind: MovementKind | None = None
    ) -> list[Movement]:
        query = select(MovementRow).where(
            MovementRow.occurred_on >= date_from, MovementRow.occurred_on <= date_to
        )
        if kind is not None:
            query = query.where(MovementRow.kind == kind.value)
        rows = await self._session.scalars(
            query.order_by(MovementRow.occurred_on, MovementRow.recorded_at, MovementRow.id)
        )
        return [_to_movement(row) for row in rows]


def _to_movement(row: MovementRow) -> Movement:
    return Movement(
        id=row.id,
        product_id=row.product_id,
        kind=MovementKind(row.kind),
        quantity=row.quantity,
        occurred_on=row.occurred_on,
        recorded_by=row.recorded_by,
        recorded_at=row.recorded_at,
        event_id=row.event_id,
        unit_cost_cents=row.unit_cost_cents,
        supplier_id=row.supplier_id,
        lot=row.lot,
        expires_on=row.expires_on,
        reason=row.reason,
        purchase_id=row.purchase_id,
    )
