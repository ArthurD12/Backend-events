"""Forma de los ingresos y egresos de caja en la API (HU21)."""

from datetime import date, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.ledger.application.ports.movement_repository import MovementEntry
from local_eventos.modules.ledger.application.use_cases.movements import (
    MovementPage,
    MovementRequest,
)
from local_eventos.modules.ledger.domain.movement import MovementCategory, MovementType
from local_eventos.modules.ledger.domain.payment import PaymentMethod


class MovementIn(BaseModel):
    type: MovementType
    category: MovementCategory = Field(
        description="Egreso: SUPPLIES, STAFF, TRANSPORT u OTHER_EXPENSE. Ingreso: OTHER_INCOME"
    )
    concept: str
    amount_cents: int
    method: PaymentMethod
    reference: str | None = None
    occurred_on: date = Field(description="No puede ser futura (R-PAG-4)")
    event_id: UUID | None = Field(default=None, description="Evento asociado, si lo hay (RN16)")

    def to_request(self, recorded_by: UUID) -> MovementRequest:
        return MovementRequest(
            type=self.type,
            category=self.category,
            concept=self.concept,
            amount_cents=self.amount_cents,
            method=self.method,
            reference=self.reference,
            occurred_on=self.occurred_on,
            event_id=self.event_id,
            recorded_by=recorded_by,
        )


class MovementVoidIn(BaseModel):
    reason: str = Field(description="Motivo obligatorio (RN17)")


class MovementVoidOut(BaseModel):
    reason: str
    voided_by: UUID
    voided_by_name: str
    voided_at: datetime


class MovementOut(BaseModel):
    id: UUID
    type: MovementType
    category: MovementCategory
    concept: str
    amount_cents: int
    currency: str = "PEN"
    method: PaymentMethod
    reference: str | None
    occurred_on: date
    event_id: UUID | None
    recorded_by: UUID
    recorded_by_name: str = Field(description="Vacío si el usuario no existe")
    recorded_at: datetime
    void: MovementVoidOut | None = Field(description="Anulado: no entra en los cálculos")

    @classmethod
    def from_entry(cls, entry: MovementEntry, names: dict[UUID, str]) -> Self:
        movement, void = entry.movement, entry.void
        return cls(
            id=movement.id,
            type=movement.type,
            category=movement.category,
            concept=movement.concept,
            amount_cents=movement.amount_cents,
            method=movement.method,
            reference=movement.reference,
            occurred_on=movement.occurred_on,
            event_id=movement.event_id,
            recorded_by=movement.recorded_by,
            recorded_by_name=names.get(movement.recorded_by, ""),
            recorded_at=movement.recorded_at,
            void=MovementVoidOut(
                reason=void.reason,
                voided_by=void.voided_by,
                voided_by_name=names.get(void.voided_by, ""),
                voided_at=void.voided_at,
            )
            if void
            else None,
        )


class MovementPageOut(BaseModel):
    items: list[MovementOut]
    total: int
    page: int
    page_size: int

    @classmethod
    def from_page(cls, page: MovementPage, names: dict[UUID, str]) -> Self:
        return cls(
            items=[MovementOut.from_entry(e, names) for e in page.items],
            total=page.total,
            page=page.page,
            page_size=page.page_size,
        )


def user_ids(entries: list[MovementEntry]) -> set[UUID]:
    ids = {e.movement.recorded_by for e in entries}
    return ids | {e.void.voided_by for e in entries if e.void}
