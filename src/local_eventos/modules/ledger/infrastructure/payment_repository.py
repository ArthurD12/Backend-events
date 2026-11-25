"""Pagos y anulaciones en PostgreSQL: solo inserta y lee (AGENTS.md, regla 5)."""

from datetime import date
from uuid import UUID

from sqlalchemy import extract, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.ledger.application.errors import PaymentAlreadyVoidedError
from local_eventos.modules.ledger.application.ports.payment_repository import (
    MonthlyPaymentTotal,
    PaymentEntry,
)
from local_eventos.modules.ledger.domain.payment import (
    Payment,
    PaymentKind,
    PaymentMethod,
    PaymentVoid,
)
from local_eventos.modules.ledger.infrastructure.orm_models import (
    PaymentCounterRow,
    PaymentRow,
    PaymentVoidRow,
)


class SqlAlchemyPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, payment: Payment) -> None:
        self._session.add(
            PaymentRow(
                id=payment.id,
                number=payment.number,
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

    async def next_number(self, year: int) -> int:
        statement = (
            insert(PaymentCounterRow)
            .values(year=year, last=1)
            .on_conflict_do_update(
                index_elements=[PaymentCounterRow.year],
                set_={"last": PaymentCounterRow.last + 1},
            )
            .returning(PaymentCounterRow.last)
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def get(self, payment_id: UUID) -> PaymentEntry | None:
        result = await self._session.execute(
            select(PaymentRow, PaymentVoidRow)
            .outerjoin(PaymentVoidRow, PaymentVoidRow.payment_id == PaymentRow.id)
            .where(PaymentRow.id == payment_id)
        )
        found = result.first()
        return _to_entry(found[0], found[1]) if found else None

    async def list_for_contract(self, contract_id: UUID) -> list[Payment]:
        return [e.payment for e in await self.entries_for_contract(contract_id)]

    async def entries_for_contract(self, contract_id: UUID) -> list[PaymentEntry]:
        result = await self._session.execute(
            select(PaymentRow, PaymentVoidRow)
            .outerjoin(PaymentVoidRow, PaymentVoidRow.payment_id == PaymentRow.id)
            .where(PaymentRow.contract_id == contract_id)
            .order_by(PaymentRow.recorded_at, PaymentRow.number)
        )
        return [_to_entry(row, void) for row, void in result]

    async def add_void(self, void: PaymentVoid) -> None:
        self._session.add(
            PaymentVoidRow(
                payment_id=void.payment_id,
                reason=void.reason,
                voided_by=void.voided_by,
                voided_at=void.voided_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as error:
            # Dos personas anulando el mismo pago a la vez: gana una.
            if "pk_ledger_payment_voids" in str(error.orig):
                raise PaymentAlreadyVoidedError() from error
            raise

    async def monthly_totals(self, date_from: date, date_to: date) -> list[MonthlyPaymentTotal]:
        year = extract("year", PaymentRow.paid_on)
        month = extract("month", PaymentRow.paid_on)
        result = await self._session.execute(
            select(year, month, PaymentRow.kind, func.sum(PaymentRow.amount_cents))
            .outerjoin(PaymentVoidRow, PaymentVoidRow.payment_id == PaymentRow.id)
            .where(
                PaymentVoidRow.payment_id.is_(None),
                PaymentRow.paid_on >= date_from,
                PaymentRow.paid_on <= date_to,
            )
            .group_by(year, month, PaymentRow.kind)
        )
        return [
            MonthlyPaymentTotal(
                year=int(y), month=int(m), kind=PaymentKind(kind), amount_cents=int(total)
            )
            for y, m, kind, total in result
        ]


def _to_entry(row: PaymentRow, void: PaymentVoidRow | None) -> PaymentEntry:
    return PaymentEntry(
        payment=Payment(
            id=row.id,
            number=row.number,
            contract_id=row.contract_id,
            kind=PaymentKind(row.kind),
            amount_cents=row.amount_cents,
            method=PaymentMethod(row.method),
            reference=row.reference,
            paid_on=row.paid_on,
            recorded_by=row.recorded_by,
            recorded_at=row.recorded_at,
        ),
        void=PaymentVoid(
            payment_id=void.payment_id,
            reason=void.reason,
            voided_by=void.voided_by,
            voided_at=void.voided_at,
        )
        if void is not None
        else None,
    )
