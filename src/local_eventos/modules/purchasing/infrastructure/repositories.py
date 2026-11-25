"""Proveedores y compras en PostgreSQL: implementan los puertos de `application`."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.purchasing.application.errors import DocumentTakenError
from local_eventos.modules.purchasing.application.ports.repositories import PurchaseFilters
from local_eventos.modules.purchasing.application.search_text import (
    WITH_ACCENTS,
    WITHOUT_ACCENTS,
    normalize,
)
from local_eventos.modules.purchasing.domain.purchase import (
    Purchase,
    PurchaseLine,
    PurchaseStatus,
    Stamp,
)
from local_eventos.modules.purchasing.domain.supplier import DocumentType, Supplier
from local_eventos.modules.purchasing.infrastructure.orm_models import (
    PurchaseCounterRow,
    PurchaseLineRow,
    PurchaseRow,
    SupplierRow,
)


class SqlAlchemySupplierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, supplier_id: UUID) -> Supplier | None:
        row = await self._session.get(SupplierRow, supplier_id)
        return _to_supplier(row) if row is not None else None

    async def get_many(self, supplier_ids: list[UUID]) -> list[Supplier]:
        if not supplier_ids:
            return []
        rows = await self._session.scalars(
            select(SupplierRow).where(SupplierRow.id.in_(supplier_ids))
        )
        return [_to_supplier(row) for row in rows]

    async def get_by_document(self, document_type: DocumentType, number: str) -> Supplier | None:
        row = await self._session.scalar(
            select(SupplierRow).where(
                SupplierRow.document_type == document_type.value,
                SupplierRow.document_number == number,
            )
        )
        return _to_supplier(row) if row is not None else None

    async def add(self, supplier: Supplier) -> None:
        row = SupplierRow(id=supplier.id)
        _copy_supplier(supplier, row)
        self._session.add(row)
        await self._flush()

    async def update(self, supplier: Supplier) -> None:
        row = await self._session.get(SupplierRow, supplier.id)
        if row is None:
            raise LookupError(f"El proveedor {supplier.id} no existe en la base de datos.")
        _copy_supplier(supplier, row)
        await self._flush()

    async def search(self, text: str, *, include_inactive: bool, limit: int) -> list[Supplier]:
        query = select(SupplierRow)
        if not include_inactive:
            query = query.where(SupplierRow.active.is_(True))
        if text:
            name = func.translate(func.lower(SupplierRow.name), WITH_ACCENTS, WITHOUT_ACCENTS)
            query = query.where(
                or_(
                    name.contains(normalize(text), autoescape=True),
                    SupplierRow.document_number.contains(text, autoescape=True),
                )
            )
        rows = await self._session.scalars(query.order_by(SupplierRow.name).limit(limit))
        return [_to_supplier(row) for row in rows]

    async def _flush(self) -> None:
        """Dos personas registrando el mismo documento a la vez: gana la restricción UNIQUE."""
        try:
            await self._session.flush()
        except IntegrityError as error:
            if "uq_purchasing_suppliers_document_type" in str(error.orig):
                raise DocumentTakenError() from error
            raise


class SqlAlchemyPurchaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, purchase_id: UUID, *, for_update: bool = False) -> Purchase | None:
        query = select(PurchaseRow).where(PurchaseRow.id == purchase_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = await self._session.scalar(query)
        if row is None:
            return None
        return (await self._to_purchases([row]))[0]

    async def add(self, purchase: Purchase) -> None:
        row = PurchaseRow(id=purchase.id, code=purchase.code)
        _copy_purchase(purchase, row)
        self._session.add(row)
        await self._session.flush()  # primero la compra: la FK de sus líneas lo exige
        self._session.add_all(
            PurchaseLineRow(
                purchase_id=purchase.id,
                position=position,
                product_id=line.product_id,
                quantity=line.quantity,
                unit_cost_cents=line.unit_cost_cents,
                received_quantity=line.received_quantity,
                lot=line.lot,
                expires_on=line.expires_on,
            )
            for position, line in enumerate(purchase.lines, start=1)
        )
        await self._session.flush()

    async def update(self, purchase: Purchase) -> None:
        """Las líneas no se agregan ni se quitan: solo reciben costo y lo recibido."""
        row = await self._session.get(PurchaseRow, purchase.id)
        if row is None:
            raise LookupError(f"La compra {purchase.id} no existe en la base de datos.")
        _copy_purchase(purchase, row)
        lines = await self._session.scalars(
            select(PurchaseLineRow)
            .where(PurchaseLineRow.purchase_id == purchase.id)
            .order_by(PurchaseLineRow.position)
        )
        for line_row, line in zip(lines, purchase.lines, strict=True):
            line_row.unit_cost_cents = line.unit_cost_cents
            line_row.received_quantity = line.received_quantity
            line_row.lot = line.lot
            line_row.expires_on = line.expires_on
        await self._session.flush()

    async def next_number(self, year: int) -> int:
        statement = (
            insert(PurchaseCounterRow)
            .values(year=year, last=1)
            .on_conflict_do_update(
                index_elements=[PurchaseCounterRow.year],
                set_={"last": PurchaseCounterRow.last + 1},
            )
            .returning(PurchaseCounterRow.last)
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def search(
        self, filters: PurchaseFilters, *, limit: int, offset: int
    ) -> tuple[list[Purchase], int]:
        conditions = []
        if filters.status is not None:
            conditions.append(PurchaseRow.status == filters.status.value)
        if filters.event_id is not None:
            conditions.append(PurchaseRow.event_id == filters.event_id)
        if filters.supplier_id is not None:
            conditions.append(PurchaseRow.supplier_id == filters.supplier_id)
        total = await self._session.scalar(
            select(func.count()).select_from(PurchaseRow).where(*conditions)
        )
        rows = list(
            await self._session.scalars(
                select(PurchaseRow)
                .where(*conditions)
                .order_by(PurchaseRow.created_at.desc(), PurchaseRow.code.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return await self._to_purchases(rows), int(total or 0)

    async def _to_purchases(self, rows: list[PurchaseRow]) -> list[Purchase]:
        if not rows:
            return []
        line_rows = await self._session.scalars(
            select(PurchaseLineRow)
            .where(PurchaseLineRow.purchase_id.in_([r.id for r in rows]))
            .order_by(PurchaseLineRow.purchase_id, PurchaseLineRow.position)
            .execution_options(populate_existing=True)
        )
        lines: dict[UUID, list[PurchaseLine]] = {}
        for lr in line_rows:
            lines.setdefault(lr.purchase_id, []).append(
                PurchaseLine(
                    product_id=lr.product_id,
                    quantity=lr.quantity,
                    unit_cost_cents=lr.unit_cost_cents,
                    received_quantity=lr.received_quantity,
                    lot=lr.lot,
                    expires_on=lr.expires_on,
                )
            )
        return [_to_purchase(row, lines.get(row.id, [])) for row in rows]


def _stamp(by: UUID | None, at: datetime | None) -> Stamp | None:
    return Stamp(by, at) if by is not None and at is not None else None


def _to_purchase(row: PurchaseRow, lines: list[PurchaseLine]) -> Purchase:
    return Purchase(
        id=row.id,
        code=row.code,
        status=PurchaseStatus(row.status),
        lines=tuple(lines),
        created=Stamp(row.created_by, row.created_at),
        event_id=row.event_id,
        notes=row.notes,
        supplier_id=row.supplier_id,
        ordered=_stamp(row.ordered_by, row.ordered_at),
        invoice_number=row.invoice_number,
        received=_stamp(row.received_by, row.received_at),
        cancelled=_stamp(row.cancelled_by, row.cancelled_at),
        cancel_reason=row.cancel_reason,
    )


def _copy_purchase(purchase: Purchase, row: PurchaseRow) -> None:
    row.status = purchase.status.value
    row.event_id = purchase.event_id
    row.notes = purchase.notes
    row.supplier_id = purchase.supplier_id
    row.invoice_number = purchase.invoice_number
    row.created_by, row.created_at = purchase.created.by, purchase.created.at
    row.ordered_by = purchase.ordered.by if purchase.ordered else None
    row.ordered_at = purchase.ordered.at if purchase.ordered else None
    row.received_by = purchase.received.by if purchase.received else None
    row.received_at = purchase.received.at if purchase.received else None
    row.cancelled_by = purchase.cancelled.by if purchase.cancelled else None
    row.cancelled_at = purchase.cancelled.at if purchase.cancelled else None
    row.cancel_reason = purchase.cancel_reason


def _to_supplier(row: SupplierRow) -> Supplier:
    return Supplier(
        id=row.id,
        name=row.name,
        document_type=DocumentType(row.document_type),
        document_number=row.document_number,
        phone=row.phone,
        contact_name=row.contact_name,
        email=row.email,
        address=row.address,
        active=row.active,
    )


def _copy_supplier(supplier: Supplier, row: SupplierRow) -> None:
    row.name = supplier.name
    row.document_type = supplier.document_type.value
    row.document_number = supplier.document_number
    row.phone = supplier.phone
    row.contact_name = supplier.contact_name
    row.email = supplier.email
    row.address = supplier.address
    row.active = supplier.active
