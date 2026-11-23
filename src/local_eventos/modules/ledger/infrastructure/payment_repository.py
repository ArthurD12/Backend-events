"""Pagos en PostgreSQL: solo inserta y lee (AGENTS.md, regla 5)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.ledger.domain.payment import Payment, PaymentKind, PaymentMethod
from local_eventos.modules.ledger.infrastructure.orm_models import PaymentRow


class SqlAlchemyPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, payment: Payment) -> None:
        self._session.add(
            PaymentRow(
                id=payment.id,
                contract_id=payment.contract_id,
                kind=payment.kind.value,
                amount_cents=payment.amount_cents,
                method=payment.method.value,
                reference=payment.reference,
                paid_on=payment.paid_on,
                recorded_by=payment.recorded_by,
                recorded_at=payment.recorded_at,
            )
        )
        await self._session.flush()

    async def list_for_contract(self, contract_id: UUID) -> list[Payment]:
        rows = await self._session.scalars(
            select(PaymentRow)
            .where(PaymentRow.contract_id == contract_id)
            .order_by(PaymentRow.recorded_at, PaymentRow.id)
        )
        return [
            Payment(
                id=row.id,
                contract_id=row.contract_id,
                kind=PaymentKind(row.kind),
                amount_cents=row.amount_cents,
                method=PaymentMethod(row.method),
                reference=row.reference,
                paid_on=row.paid_on,
                recorded_by=row.recorded_by,
                recorded_at=row.recorded_at,
            )
            for row in rows
        ]
