"""Ensamblaje del módulo ledger: único lugar que conoce las clases de `infrastructure`."""

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.ledger.application.ports.clock import Clock
from local_eventos.modules.ledger.application.ports.movement_repository import MovementRepository
from local_eventos.modules.ledger.application.ports.payment_repository import PaymentRepository
from local_eventos.modules.ledger.infrastructure.clock import LimaClock
from local_eventos.modules.ledger.infrastructure.movement_repository import (
    SqlAlchemyMovementRepository,
)
from local_eventos.modules.ledger.infrastructure.payment_repository import (
    SqlAlchemyPaymentRepository,
)


def payment_repository(session: AsyncSession) -> PaymentRepository:
    return SqlAlchemyPaymentRepository(session)


def movement_repository(session: AsyncSession) -> MovementRepository:
    return SqlAlchemyMovementRepository(session)


def clock() -> Clock:
    return LimaClock()
