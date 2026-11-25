"""Indisponibilidades en PostgreSQL (HU16): implementa `UnavailabilityRepository`."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.staff.domain.period import Period
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.infrastructure.orm_models import UnavailabilityRow
from local_eventos.modules.staff.infrastructure.periods import to_period, to_range


class SqlAlchemyUnavailabilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, unavailability_id: UUID) -> Unavailability | None:
        row = await self._session.get(UnavailabilityRow, unavailability_id)
        return _to_unavailability(row) if row is not None else None

    async def add(self, unavailability: Unavailability) -> None:
        self._session.add(
            UnavailabilityRow(
                id=unavailability.id,
                worker_id=unavailability.worker_id,
                period=to_range(unavailability.period),
                reason=unavailability.reason,
                created_by=unavailability.created_by,
                created_at=unavailability.created_at,
            )
        )
        await self._session.flush()

    async def remove(self, unavailability_id: UUID) -> None:
        await self._session.execute(
            delete(UnavailabilityRow).where(UnavailabilityRow.id == unavailability_id)
        )

    async def list_for_worker(self, worker_id: UUID) -> list[Unavailability]:
        rows = await self._session.scalars(
            select(UnavailabilityRow)
            .where(UnavailabilityRow.worker_id == worker_id)
            .order_by(UnavailabilityRow.period)
        )
        return [_to_unavailability(row) for row in rows]

    async def list_overlapping(
        self, period: Period, *, worker_id: UUID | None = None
    ) -> list[Unavailability]:
        query = select(UnavailabilityRow).where(UnavailabilityRow.period.overlaps(to_range(period)))
        if worker_id is not None:
            query = query.where(UnavailabilityRow.worker_id == worker_id)
        rows = await self._session.scalars(query.order_by(UnavailabilityRow.period))
        return [_to_unavailability(row) for row in rows]


def _to_unavailability(row: UnavailabilityRow) -> Unavailability:
    return Unavailability(
        id=row.id,
        worker_id=row.worker_id,
        period=to_period(row.period),
        reason=row.reason,
        created_by=row.created_by,
        created_at=row.created_at,
    )
