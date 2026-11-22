"""Ensamblaje del módulo ledger: único lugar que conoce las clases de `infrastructure`."""

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.ledger.application.ports.payment_repository import PaymentRepository
from local_eventos.modules.ledger.infrastructure.payment_repository import (
    SqlAlchemyPaymentRepository,
)


def payment_repository(session: AsyncSession) -> PaymentRepository:
    return SqlAlchemyPaymentRepository(session)
