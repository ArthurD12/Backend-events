"""Ingresos, egresos y anulaciones en PostgreSQL: solo inserta y lee (AGENTS.md, regla 5)."""

from datetime import date
from uuid import UUID

from sqlalchemy import ColumnElement, extract, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.ledger.application.errors import MovementAlreadyVoidedError
from local_eventos.modules.ledger.application.ports.movement_repository import (
    MonthlyMovementTotal,
    MovementEntry,
    MovementFilters,
    MovementState,
)
from local_eventos.modules.ledger.domain.movement import (
    CashMovement,
    MovementCategory,
    MovementType,
    MovementVoid,
)
from local_eventos.modules.ledger.domain.payment import PaymentMethod
from local_eventos.modules.ledger.infrastructure.orm_models import MovementRow, MovementVoidRow


class SqlAlchemyMovementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, movement: CashMovement) -> None:
        self._session.add(
            MovementRow(
                id=movement.id,
                type=movement.type.value,
                category=movement.category.value,
                concept=movement.concept,
                amount_cents=movement.amount_cents,
                method=movement.method.value,
                reference=movement.reference,
                occurred_on=movement.occurred_on,
                event_id=movement.event_id,
                recorded_by=movement.recorded_by,
                recorded_at=movement.recorded_at,
            )
        )
        await self._session.flush()

    async def get(self, movement_id: UUID) -> MovementEntry | None:
        result = await self._session.execute(
            select(MovementRow, MovementVoidRow)
            .outerjoin(MovementVoidRow, MovementVoidRow.movement_id == MovementRow.id)
            .where(MovementRow.id == movement_id)
        )
        found = result.first()
        return _to_entry(found[0], found[1]) if found else None

    async def add_void(self, void: MovementVoid) -> None:
        self._session.add(
            MovementVoidRow(
                movement_id=void.movement_id,
                reason=void.reason,
                voided_by=void.voided_by,
                voided_at=void.voided_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as error:
            if "pk_ledger_movement_voids" in str(error.orig):
                raise MovementAlreadyVoidedError() from error
            raise

    async def search(
        self, filters: MovementFilters, *, limit: int, offset: int
    ) -> tuple[list[MovementEntry], int]:
        conditions = _conditions(filters)
        result = await self._session.execute(
            select(MovementRow, MovementVoidRow)
            .outerjoin(MovementVoidRow, MovementVoidRow.movement_id == MovementRow.id)
            .where(*conditions)
            .order_by(MovementRow.occurred_on.desc(), MovementRow.recorded_at.desc())
            .limit(limit)
            .offset(offset)
        )
        total = await self._session.scalar(
            select(func.count())
            .select_from(MovementRow)
            .outerjoin(MovementVoidRow, MovementVoidRow.movement_id == MovementRow.id)
            .where(*conditions)
        )
        return [_to_entry(row, void) for row, void in result], int(total or 0)

    async def monthly_totals(self, date_from: date, date_to: date) -> list[MonthlyMovementTotal]:
        year = extract("year", MovementRow.occurred_on)
        month = extract("month", MovementRow.occurred_on)
        result = await self._session.execute(
            select(year, month, MovementRow.category, func.sum(MovementRow.amount_cents))
            .outerjoin(MovementVoidRow, MovementVoidRow.movement_id == MovementRow.id)
            .where(
                MovementVoidRow.movement_id.is_(None),
                MovementRow.occurred_on >= date_from,
                MovementRow.occurred_on <= date_to,
            )
            .group_by(year, month, MovementRow.category)
        )
        return [
            MonthlyMovementTotal(
                year=int(y),
                month=int(m),
                category=MovementCategory(category),
                amount_cents=int(total),
            )
            for y, m, category, total in result
        ]

    async def event_totals(self, event_id: UUID) -> dict[MovementCategory, int]:
        result = await self._session.execute(
            select(MovementRow.category, func.sum(MovementRow.amount_cents))
            .outerjoin(MovementVoidRow, MovementVoidRow.movement_id == MovementRow.id)
            .where(MovementVoidRow.movement_id.is_(None), MovementRow.event_id == event_id)
            .group_by(MovementRow.category)
        )
        return {MovementCategory(category): int(total) for category, total in result}


def _conditions(filters: MovementFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.date_from is not None:
        conditions.append(MovementRow.occurred_on >= filters.date_from)
    if filters.date_to is not None:
        conditions.append(MovementRow.occurred_on <= filters.date_to)
    if filters.type is not None:
        conditions.append(MovementRow.type == filters.type.value)
    if filters.category is not None:
        conditions.append(MovementRow.category == filters.category.value)
    if filters.event_id is not None:
        conditions.append(MovementRow.event_id == filters.event_id)
    if filters.state is MovementState.ACTIVE:
        conditions.append(MovementVoidRow.movement_id.is_(None))
    elif filters.state is MovementState.VOIDED:
        conditions.append(MovementVoidRow.movement_id.is_not(None))
    return conditions


def _to_entry(row: MovementRow, void: MovementVoidRow | None) -> MovementEntry:
    return MovementEntry(
        movement=CashMovement(
            id=row.id,
            type=MovementType(row.type),
            category=MovementCategory(row.category),
            concept=row.concept,
            amount_cents=row.amount_cents,
            method=PaymentMethod(row.method),
            reference=row.reference,
            occurred_on=row.occurred_on,
            event_id=row.event_id,
            recorded_by=row.recorded_by,
            recorded_at=row.recorded_at,
        ),
        void=MovementVoid(
            movement_id=void.movement_id,
            reason=void.reason,
            voided_by=void.voided_by,
            voided_at=void.voided_at,
        )
        if void is not None
        else None,
    )
