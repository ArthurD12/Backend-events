"""Reservas en PostgreSQL. La reserva vigente se actualiza; las cerradas quedan como historia."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.inventory.domain.reservation import Reservation, ReservationStatus
from local_eventos.modules.inventory.infrastructure.orm_models import ReservationRow

_ACTIVE = ReservationStatus.ACTIVE.value


class SqlAlchemyReservationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def active_for_event(self, event_id: UUID) -> list[Reservation]:
        rows = await self._session.scalars(
            select(ReservationRow)
            .where(ReservationRow.event_id == event_id, ReservationRow.status == _ACTIVE)
            .execution_options(populate_existing=True)
        )
        return [_to_reservation(row) for row in rows]

    async def get_active(self, event_id: UUID, product_id: UUID) -> Reservation | None:
        row = await self._session.scalar(
            select(ReservationRow)
            .where(
                ReservationRow.event_id == event_id,
                ReservationRow.product_id == product_id,
                ReservationRow.status == _ACTIVE,
            )
            .execution_options(populate_existing=True)
        )
        return None if row is None else _to_reservation(row)

    async def active_totals(self, product_ids: list[UUID]) -> dict[UUID, Decimal]:
        if not product_ids:
            return {}
        rows = await self._session.execute(
            select(ReservationRow.product_id, func.sum(ReservationRow.quantity))
            .where(ReservationRow.product_id.in_(product_ids), ReservationRow.status == _ACTIVE)
            .group_by(ReservationRow.product_id)
        )
        return {product_id: total for product_id, total in rows}

    async def save(self, reservation: Reservation) -> None:
        row = await self._session.get(ReservationRow, reservation.id)
        if row is None:
            row = ReservationRow(
                id=reservation.id,
                event_id=reservation.event_id,
                product_id=reservation.product_id,
                created_by=reservation.created_by,
                created_at=reservation.created_at,
            )
            self._session.add(row)
        row.quantity = reservation.quantity
        row.status = reservation.status.value
        row.closed_at = reservation.closed_at
        await self._session.flush()

    async def release_event(self, event_id: UUID, now: datetime) -> int:
        result = await self._session.execute(
            update(ReservationRow)
            .where(ReservationRow.event_id == event_id, ReservationRow.status == _ACTIVE)
            .values(status=ReservationStatus.RELEASED.value, closed_at=now)
        )
        await self._session.flush()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]


def _to_reservation(row: ReservationRow) -> Reservation:
    return Reservation(
        id=row.id,
        event_id=row.event_id,
        product_id=row.product_id,
        quantity=row.quantity,
        status=ReservationStatus(row.status),
        created_by=row.created_by,
        created_at=row.created_at,
        closed_at=row.closed_at,
    )
