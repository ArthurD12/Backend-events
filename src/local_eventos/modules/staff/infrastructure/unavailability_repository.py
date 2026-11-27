"""Repositorio de indisponibilidades en PostgreSQL (HU16, T-08): implementa el puerto.

Traduce entre el agregado `Unavailability`/`UnavailabilityAudit` y las filas ORM
mediante `mappers.py`; nunca devuelve filas al exterior. No confirma la transacción:
la gestión la decide quien abre la sesión, para que la indisponibilidad y su
auditoría se guarden juntas o no se guarde ninguna (plan §5.5).

Los listados son de solo lectura. El solape de indisponibilidades es una consulta
propia sobre `staff_unavailabilities` con el mismo predicado semiabierto que HU17
(`start_at < fin AND end_at > inicio`), pero no reimplementa ni modifica el SQL de
asignaciones (plan §2.4).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from local_eventos.modules.staff.domain.enums import UnavailabilityStatus
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.unavailability_audit import UnavailabilityAudit
from local_eventos.modules.staff.infrastructure.mappers import (
    row_to_unavailability,
    unavailability_audit_to_row,
    unavailability_to_row,
)
from local_eventos.modules.staff.infrastructure.orm_models import (
    StaffUnavailabilityRow,
)


class SqlAlchemyUnavailabilityRepository:
    """Implementación async del puerto sobre la sesión de SQLAlchemy de la petición."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, unavailability: Unavailability, audit: UnavailabilityAudit) -> None:
        """Inserta o actualiza la indisponibilidad y añade su auditoría en la misma sesión."""
        row = await self._session.get(StaffUnavailabilityRow, unavailability.id)
        if row is None:
            self._session.add(unavailability_to_row(unavailability))
        else:
            # Solo campos editables: `worker_id` es inmutable y el trigger de la
            # base lo protege si algo intentara cambiarlo.
            row.kind = unavailability.kind.value
            row.description = unavailability.description
            row.start_at = unavailability.start_at
            row.end_at = unavailability.end_at
            row.status = unavailability.status.value
        # La indisponibilidad se escribe antes que su auditoría para que la FK resuelva.
        await self._session.flush()
        self._session.add(unavailability_audit_to_row(audit))
        await self._session.flush()

    async def get(self, unavailability_id: UUID) -> Unavailability | None:
        """Devuelve la indisponibilidad por id, o `None` si no existe."""
        row = await self._session.get(StaffUnavailabilityRow, unavailability_id)
        return row_to_unavailability(row) if row is not None else None

    async def get_for_update(self, unavailability_id: UUID) -> Unavailability | None:
        """Lectura con `FOR UPDATE` para editar o anular sin carreras."""
        row = await self._session.scalar(
            select(StaffUnavailabilityRow)
            .where(StaffUnavailabilityRow.id == unavailability_id)
            .with_for_update()
        )
        return row_to_unavailability(row) if row is not None else None

    async def list_active_overlapping(
        self,
        start_at: datetime,
        end_at: datetime,
        worker_ids: Sequence[UUID],
    ) -> list[Unavailability]:
        """Indisponibilidades `ACTIVE` que se cruzan con la ventana, por trabajador."""
        if not worker_ids:
            return []
        rows = await self._session.scalars(
            select(StaffUnavailabilityRow)
            .where(
                StaffUnavailabilityRow.status == UnavailabilityStatus.ACTIVE.value,
                StaffUnavailabilityRow.start_at < end_at,
                StaffUnavailabilityRow.end_at > start_at,
                StaffUnavailabilityRow.worker_id.in_(worker_ids),
            )
            .order_by(StaffUnavailabilityRow.start_at)
        )
        return [row_to_unavailability(row) for row in rows]

    async def list_by_worker(
        self,
        worker_id: UUID,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[Unavailability]:
        """Indisponibilidades de un trabajador, incluidas las anuladas."""
        query = select(StaffUnavailabilityRow).where(StaffUnavailabilityRow.worker_id == worker_id)
        query = query.where(*_overlap_filters(start_at, end_at))
        query = query.order_by(StaffUnavailabilityRow.start_at)
        rows = await self._session.scalars(query)
        return [row_to_unavailability(row) for row in rows]

    async def list(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[Unavailability]:
        """Indisponibilidades de todos los trabajadores, filtrables por ventana."""
        query = select(StaffUnavailabilityRow).where(*_overlap_filters(start_at, end_at))
        query = query.order_by(StaffUnavailabilityRow.start_at)
        rows = await self._session.scalars(query)
        return [row_to_unavailability(row) for row in rows]


def _overlap_filters(
    start_at: datetime | None, end_at: datetime | None
) -> list[ColumnElement[bool]]:
    """Restringe a las que se cruzan con la ventana semiabierta si se indicó."""
    filters: list[ColumnElement[bool]] = []
    if start_at is not None:
        filters.append(StaffUnavailabilityRow.end_at > start_at)
    if end_at is not None:
        filters.append(StaffUnavailabilityRow.start_at < end_at)
    return filters
