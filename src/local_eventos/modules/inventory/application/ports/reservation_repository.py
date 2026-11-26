"""Puerto del repositorio de reservas."""

from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from local_eventos.modules.inventory.domain.reservation import Reservation


class ReservationRepository(Protocol):
    async def active_for_event(self, event_id: UUID) -> list[Reservation]: ...

    async def get_active(self, event_id: UUID, product_id: UUID) -> Reservation | None: ...

    async def active_totals(self, product_ids: list[UUID]) -> dict[UUID, Decimal]:
        """Reservado vigente por producto (todos los eventos); los sin reserva no aparecen."""
        ...

    async def save(self, reservation: Reservation) -> None:
        """Inserta la reserva o actualiza su cantidad y estado."""
        ...

    async def release_event(self, event_id: UUID, now: datetime) -> int:
        """Libera las reservas vigentes del evento y devuelve cuántas eran."""
        ...
