"""Ingreso o egreso de caja que no es pago de un cliente (HU21, RN16). Inmutable.

Un egreso se clasifica (insumos, personal, transporte, otros) y puede asociarse a un evento por
su ID, sin FK entre módulos. Se corrige anulándolo con motivo (RN17), nunca editándolo.
Python puro: no importa FastAPI, SQLAlchemy ni Pydantic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from local_eventos.modules.ledger.domain.payment import (
    LedgerValidationError,
    PaymentMethod,
    check_reason,
    clean_reference,
)

_CONCEPT_MAX_LENGTH = 200


class MovementType(StrEnum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class MovementCategory(StrEnum):
    SUPPLIES = "SUPPLIES"  # insumos
    STAFF = "STAFF"  # personal (R-PAG-3)
    TRANSPORT = "TRANSPORT"
    OTHER_EXPENSE = "OTHER_EXPENSE"
    OTHER_INCOME = "OTHER_INCOME"  # p. ej., alquiler de menaje (CA-21.2)


CATEGORIES_BY_TYPE: dict[MovementType, frozenset[MovementCategory]] = {
    MovementType.EXPENSE: frozenset(
        {
            MovementCategory.SUPPLIES,
            MovementCategory.STAFF,
            MovementCategory.TRANSPORT,
            MovementCategory.OTHER_EXPENSE,
        }
    ),
    MovementType.INCOME: frozenset({MovementCategory.OTHER_INCOME}),
}


@dataclass(frozen=True)
class CashMovement:
    id: UUID
    type: MovementType
    category: MovementCategory
    concept: str
    amount_cents: int
    method: PaymentMethod
    reference: str | None
    occurred_on: date
    event_id: UUID | None
    recorded_by: UUID
    recorded_at: datetime

    @classmethod
    def record(
        cls,
        *,
        type: MovementType,  # noqa: A002 - nombre del dominio
        category: MovementCategory,
        concept: str,
        amount_cents: int,
        method: PaymentMethod,
        reference: str | None,
        occurred_on: date,
        event_id: UUID | None,
        recorded_by: UUID,
        now: datetime,
        today: date,
    ) -> CashMovement:
        if category not in CATEGORIES_BY_TYPE[type]:
            raise LedgerValidationError(
                "movement.category_invalid", "La categoría no corresponde al tipo de movimiento."
            )
        cleaned = " ".join((concept or "").split())
        if not cleaned:
            raise LedgerValidationError("movement.concept_required", "Indica el concepto.")
        if len(cleaned) > _CONCEPT_MAX_LENGTH:
            raise LedgerValidationError(
                "movement.concept_too_long",
                f"El concepto no puede superar {_CONCEPT_MAX_LENGTH} caracteres.",
            )
        if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents <= 0:
            raise LedgerValidationError(
                "movement.amount_invalid", "El monto debe ser mayor que cero."
            )
        if occurred_on > today:  # R-PAG-4
            raise LedgerValidationError(
                "movement.date_in_future", "La fecha no puede ser posterior a hoy."
            )
        return cls(
            id=uuid4(),
            type=type,
            category=category,
            concept=cleaned,
            amount_cents=amount_cents,
            method=method,
            reference=clean_reference(reference, "movement"),
            occurred_on=occurred_on,
            event_id=event_id,
            recorded_by=recorded_by,
            recorded_at=now,
        )


@dataclass(frozen=True)
class MovementVoid:
    """Anulación de un movimiento (CA-21.3): una fila aparte; el movimiento no cambia."""

    movement_id: UUID
    reason: str
    voided_by: UUID
    voided_at: datetime

    @classmethod
    def of(
        cls, movement: CashMovement, *, reason: str, voided_by: UUID, now: datetime
    ) -> MovementVoid:
        """Que el movimiento no tenga ya otra anulación lo revisa aplicación."""
        return cls(
            movement_id=movement.id,
            reason=check_reason(reason, "movement"),
            voided_by=voided_by,
            voided_at=now,
        )
