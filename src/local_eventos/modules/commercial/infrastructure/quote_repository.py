"""Repositorio de cotizaciones en PostgreSQL (HU07–HU08): implementa `QuoteRepository`.

Traduce entre el agregado `Quote` y sus filas. No confirma la transacción: eso lo decide quien
abre la sesión, una vez por petición. Las líneas solo se reescriben si cambiaron: así un cambio
de estado no las toca y los triggers que protegen las cotizaciones cerradas no se activan.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import ColumnElement, and_, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.commercial.application.clients.search_text import (
    WITH_ACCENTS,
    WITHOUT_ACCENTS,
    normalize,
)
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteFilters,
    QuoteSummary,
)
from local_eventos.modules.commercial.domain.quotes.quote import (
    EventDetails,
    EventType,
    LineKind,
    LineUnit,
    Quote,
    QuoteLine,
    QuoteStatus,
)
from local_eventos.modules.commercial.infrastructure.orm_models import (
    ClientRow,
    QuoteCounterRow,
    QuoteLineRow,
    QuoteRow,
)

_OPEN = (QuoteStatus.DRAFT.value, QuoteStatus.SENT.value)


class SqlAlchemyQuoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, quote_id: UUID) -> Quote | None:
        row = await self._session.get(QuoteRow, quote_id)
        if row is None:
            return None
        return _to_quote(row, await self._lines(quote_id))

    async def add(self, quote: Quote) -> None:
        row = QuoteRow(id=quote.id, code=quote.code, created_by=quote.created_by)
        _copy_to_row(quote, row)
        row.created_at = quote.created_at
        self._session.add(row)
        await self._session.flush()  # primero la cotización (en borrador), luego sus líneas
        self._session.add_all(_line_rows(quote))
        await self._session.flush()

    async def update(self, quote: Quote) -> None:
        row = await self._session.get(QuoteRow, quote.id)
        if row is None:
            raise LookupError(f"La cotización {quote.id} no existe en la base de datos.")
        if tuple(await self._lines(quote.id)) != quote.lines:
            await self._session.execute(
                delete(QuoteLineRow).where(QuoteLineRow.quote_id == quote.id)
            )
            self._session.add_all(_line_rows(quote))
            await self._session.flush()
        _copy_to_row(quote, row)
        await self._session.flush()

    async def next_number(self, year: int) -> int:
        statement = (
            insert(QuoteCounterRow)
            .values(year=year, last=1)
            .on_conflict_do_update(
                index_elements=[QuoteCounterRow.year], set_={"last": QuoteCounterRow.last + 1}
            )
            .returning(QuoteCounterRow.last)
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def search(
        self, filters: QuoteFilters, *, today: date, limit: int, offset: int
    ) -> tuple[list[QuoteSummary], int]:
        conditions = _conditions(filters, today)
        rows = await self._session.execute(
            select(QuoteRow, ClientRow.name)
            .join(ClientRow, ClientRow.id == QuoteRow.client_id)
            .where(*conditions)
            .order_by(QuoteRow.created_at.desc(), QuoteRow.code.desc())
            .limit(limit)
            .offset(offset)
        )
        total = await self._session.scalar(
            select(func.count())
            .select_from(QuoteRow)
            .join(ClientRow, ClientRow.id == QuoteRow.client_id)
            .where(*conditions)
        )
        items = [
            QuoteSummary(
                id=row.id,
                code=row.code,
                client_id=row.client_id,
                client_name=client_name,
                event_type=EventType(row.event_type),
                event_date=row.event_date,
                guests=row.guests,
                total_cents=row.total_cents,
                status=_effective_status(row.status, row.valid_until, today),
                valid_until=row.valid_until,
            )
            for row, client_name in rows
        ]
        return items, int(total or 0)

    async def total_amount(self, filters: QuoteFilters, *, today: date) -> int:
        total = await self._session.scalar(
            select(func.coalesce(func.sum(QuoteRow.total_cents), 0))
            .select_from(QuoteRow)
            .join(ClientRow, ClientRow.id == QuoteRow.client_id)
            .where(*_conditions(filters, today))
        )
        return int(total or 0)

    async def _lines(self, quote_id: UUID) -> list[QuoteLine]:
        rows = await self._session.scalars(
            select(QuoteLineRow)
            .where(QuoteLineRow.quote_id == quote_id)
            .order_by(QuoteLineRow.position)
        )
        return [
            QuoteLine(
                kind=LineKind(row.kind),
                description=row.description,
                unit=LineUnit(row.price_unit),
                quantity=row.quantity,
                unit_price_cents=row.unit_price_cents,
                service_id=row.service_id,
                catalog_price_cents=row.catalog_price_cents,
            )
            for row in rows
        ]


def _conditions(filters: QuoteFilters, today: date) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.text:
        client_name = func.translate(func.lower(ClientRow.name), WITH_ACCENTS, WITHOUT_ACCENTS)
        conditions.append(
            or_(
                QuoteRow.code.icontains(filters.text, autoescape=True),
                client_name.contains(normalize(filters.text), autoescape=True),
            )
        )
    if filters.client_id is not None:
        conditions.append(QuoteRow.client_id == filters.client_id)
    if filters.event_date_from is not None:
        conditions.append(QuoteRow.event_date >= filters.event_date_from)
    if filters.event_date_to is not None:
        conditions.append(QuoteRow.event_date <= filters.event_date_to)
    if filters.created_from is not None:
        conditions.append(QuoteRow.created_at >= filters.created_from)
    if filters.created_to is not None:
        conditions.append(QuoteRow.created_at < filters.created_to)
    if filters.status is QuoteStatus.EXPIRED:
        conditions.append(and_(QuoteRow.status.in_(_OPEN), QuoteRow.valid_until < today))
    elif filters.status is not None:
        conditions.append(QuoteRow.status == filters.status.value)
        if filters.status.value in _OPEN:
            conditions.append(QuoteRow.valid_until >= today)
    return conditions


def _effective_status(status: str, valid_until: date, today: date) -> QuoteStatus:
    if status in _OPEN and valid_until < today:
        return QuoteStatus.EXPIRED
    return QuoteStatus(status)


def _to_quote(row: QuoteRow, lines: list[QuoteLine]) -> Quote:
    return Quote(
        id=row.id,
        code=row.code,
        client_id=row.client_id,
        details=EventDetails(
            event_type=EventType(row.event_type),
            event_date=row.event_date,
            start_time=row.start_time,
            end_time=row.end_time,
            venue=row.venue,
            guests=row.guests,
        ),
        valid_until=row.valid_until,
        lines=tuple(lines),
        status=QuoteStatus(row.status),
        created_by=row.created_by,
        created_at=row.created_at,
        notes=row.notes,
    )


def _copy_to_row(quote: Quote, row: QuoteRow) -> None:
    row.client_id = quote.client_id
    row.event_type = quote.details.event_type.value
    row.event_date = quote.details.event_date
    row.start_time = quote.details.start_time
    row.end_time = quote.details.end_time
    row.venue = quote.details.venue
    row.guests = quote.details.guests
    row.valid_until = quote.valid_until
    row.notes = quote.notes
    row.status = quote.status.value
    row.total_cents = quote.total_cents


def _line_rows(quote: Quote) -> list[QuoteLineRow]:
    return [
        QuoteLineRow(
            quote_id=quote.id,
            position=position,
            kind=line.kind.value,
            service_id=line.service_id,
            description=line.description,
            price_unit=line.unit.value,
            quantity=line.quantity,
            unit_price_cents=line.unit_price_cents,
            catalog_price_cents=line.catalog_price_cents,
            subtotal_cents=line.subtotal_cents,
        )
        for position, line in enumerate(quote.lines, start=1)
    ]
