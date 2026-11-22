"""Repositorio de contratos en PostgreSQL (HU41–HU42): implementa `ContractRepository`."""

from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial.application.clients.search_text import (
    WITH_ACCENTS,
    WITHOUT_ACCENTS,
    normalize,
)
from local_eventos.modules.commercial.application.contracts.errors import (
    ContractAlreadyExistsError,
)
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractFilters,
    ContractSummary,
)
from local_eventos.modules.commercial.domain.contracts.contract import (
    Cancellation,
    Contract,
    ContractStatus,
    Signature,
)
from local_eventos.modules.commercial.infrastructure.orm_models import (
    ClientRow,
    ContractCounterRow,
    ContractRow,
)


class SqlAlchemyContractRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, contract_id: UUID) -> Contract | None:
        row = await self._session.get(ContractRow, contract_id)
        return _to_contract(row) if row is not None else None

    async def get_by_quote(self, quote_id: UUID) -> Contract | None:
        row = await self._session.scalar(
            select(ContractRow).where(ContractRow.quote_id == quote_id)
        )
        return _to_contract(row) if row is not None else None

    async def add(self, contract: Contract) -> None:
        row = ContractRow(id=contract.id)
        _copy_to_row(contract, row)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as error:
            # Dos personas generando el contrato de la misma cotización a la vez: gana una.
            if "uq_commercial_contracts_quote_id" in str(error.orig):
                raise ContractAlreadyExistsError() from error
            raise

    async def update(self, contract: Contract) -> None:
        row = await self._session.get(ContractRow, contract.id)
        if row is None:
            raise LookupError(f"El contrato {contract.id} no existe en la base de datos.")
        _copy_to_row(contract, row)
        await self._session.flush()

    async def next_number(self, year: int) -> int:
        statement = (
            insert(ContractCounterRow)
            .values(year=year, last=1)
            .on_conflict_do_update(
                index_elements=[ContractCounterRow.year],
                set_={"last": ContractCounterRow.last + 1},
            )
            .returning(ContractCounterRow.last)
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def search(
        self, filters: ContractFilters, *, limit: int, offset: int
    ) -> tuple[list[ContractSummary], int]:
        conditions = _conditions(filters)
        rows = await self._session.execute(
            select(ContractRow, ClientRow.name)
            .join(ClientRow, ClientRow.id == ContractRow.client_id)
            .where(*conditions)
            .order_by(ContractRow.created_at.desc(), ContractRow.code.desc())
            .limit(limit)
            .offset(offset)
        )
        total = await self._session.scalar(
            select(func.count())
            .select_from(ContractRow)
            .join(ClientRow, ClientRow.id == ContractRow.client_id)
            .where(*conditions)
        )
        items = [
            ContractSummary(
                id=row.id,
                code=row.code,
                quote_id=row.quote_id,
                client_name=client_name,
                event_date=row.event_date,
                total_cents=row.total_cents,
                advance_cents=row.advance_cents,
                status=ContractStatus(row.status),
            )
            for row, client_name in rows
        ]
        return items, int(total or 0)


def _conditions(filters: ContractFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.text:
        name = func.translate(func.lower(ClientRow.name), WITH_ACCENTS, WITHOUT_ACCENTS)
        conditions.append(
            or_(
                ContractRow.code.icontains(filters.text, autoescape=True),
                name.contains(normalize(filters.text), autoescape=True),
            )
        )
    if filters.status is not None:
        conditions.append(ContractRow.status == filters.status.value)
    return conditions


def _to_contract(row: ContractRow) -> Contract:
    signature = None
    if row.signed_on is not None:
        assert row.signer_name and row.advance_payment_id and row.signature_recorded_by
        assert row.signature_recorded_at is not None
        signature = Signature(
            signed_on=row.signed_on,
            signer_name=row.signer_name,
            advance_payment_id=row.advance_payment_id,
            recorded_by=row.signature_recorded_by,
            recorded_at=row.signature_recorded_at,
        )
    cancellation = None
    if row.cancel_reason is not None:
        assert row.cancelled_by is not None and row.cancelled_at is not None
        cancellation = Cancellation(
            reason=row.cancel_reason,
            refund_cents=row.refund_cents,
            refund_payment_id=row.refund_payment_id,
            note=row.cancel_note,
            cancelled_by=row.cancelled_by,
            cancelled_at=row.cancelled_at,
        )
    return Contract(
        id=row.id,
        code=row.code,
        quote_id=row.quote_id,
        client_id=row.client_id,
        event_date=row.event_date,
        total_cents=row.total_cents,
        advance_cents=row.advance_cents,
        balance_due_date=row.balance_due_date,
        status=ContractStatus(row.status),
        created_by=row.created_by,
        created_at=row.created_at,
        signature=signature,
        cancellation=cancellation,
    )


def _copy_to_row(contract: Contract, row: ContractRow) -> None:
    row.code = contract.code
    row.quote_id = contract.quote_id
    row.client_id = contract.client_id
    row.event_date = contract.event_date
    row.total_cents = contract.total_cents
    row.advance_cents = contract.advance_cents
    row.balance_due_date = contract.balance_due_date
    row.status = contract.status.value
    row.created_by = contract.created_by
    row.created_at = contract.created_at
    signature, cancellation = contract.signature, contract.cancellation
    row.signed_on = signature.signed_on if signature else None
    row.signer_name = signature.signer_name if signature else None
    row.advance_payment_id = signature.advance_payment_id if signature else None
    row.signature_recorded_by = signature.recorded_by if signature else None
    row.signature_recorded_at = signature.recorded_at if signature else None
    row.cancel_reason = cancellation.reason if cancellation else None
    row.refund_cents = cancellation.refund_cents if cancellation else None
    row.refund_payment_id = cancellation.refund_payment_id if cancellation else None
    row.cancel_note = cancellation.note if cancellation else None
    row.cancelled_by = cancellation.cancelled_by if cancellation else None
    row.cancelled_at = cancellation.cancelled_at if cancellation else None
