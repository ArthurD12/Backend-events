"""Repositorio de eventos en PostgreSQL (HU10): implementa `EventRepository`."""

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
from local_eventos.modules.commercial.application.events.errors import EventAlreadyExistsError
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventFilters,
    EventSummary,
)
from local_eventos.modules.commercial.domain.events.event import (
    Event,
    EventCancellation,
    EventRuleError,
    EventService,
    EventStatus,
)
from local_eventos.modules.commercial.domain.quotes.quote import EventType, LineKind, LineUnit
from local_eventos.modules.commercial.infrastructure.orm_models import (
    ClientRow,
    EventCounterRow,
    EventRow,
    EventServiceRow,
)


class SqlAlchemyEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, event_id: UUID) -> Event | None:
        row = await self._session.get(EventRow, event_id)
        return await self._to_event(row) if row is not None else None

    async def get_by_contract(self, contract_id: UUID) -> Event | None:
        row = await self._session.scalar(
            select(EventRow).where(EventRow.contract_id == contract_id)
        )
        return await self._to_event(row) if row is not None else None

    async def add(self, event: Event) -> None:
        self._session.add(
            EventRow(
                id=event.id,
                code=event.code,
                contract_id=event.contract_id,
                quote_id=event.quote_id,
                client_id=event.client_id,
                event_type=event.event_type.value,
                event_date=event.event_date,
                start_time=event.start_time,
                end_time=event.end_time,
                venue=event.venue,
                guests=event.guests,
                coordinator_id=event.coordinator_id,
                status=event.status.value,
                created_by=event.created_by,
                created_at=event.created_at,
            )
        )
        try:
            await self._session.flush()  # primero el evento: la FK de sus servicios lo exige
        except IntegrityError as error:
            # Dos personas convirtiendo el mismo contrato a la vez: gana una (CA-10.5).
            if "uq_commercial_events_contract_id" in str(error.orig):
                raise EventAlreadyExistsError() from error
            # Alguien anuló el contrato mientras se convertía (CA-10.1).
            if "CA-10.1" in str(error.orig):
                raise EventRuleError(
                    "event.contract_not_ready",
                    "Solo un contrato firmado y con adelanto pagado se convierte en evento.",
                ) from error
            raise
        self._session.add_all(
            EventServiceRow(
                event_id=event.id,
                position=position,
                kind=service.kind.value,
                service_id=service.service_id,
                description=service.description,
                price_unit=service.unit.value,
                quantity=service.quantity,
            )
            for position, service in enumerate(event.services, start=1)
        )
        await self._session.flush()

    async def update(self, event: Event) -> None:
        """Por ahora solo cambia el estado y la cancelación (HU11, parte)."""
        row = await self._session.get(EventRow, event.id)
        if row is None:
            raise LookupError(f"El evento {event.id} no existe en la base de datos.")
        cancellation = event.cancellation
        row.status = event.status.value
        row.cancel_reason = cancellation.reason if cancellation else None
        row.cancelled_by = cancellation.cancelled_by if cancellation else None
        row.cancelled_at = cancellation.cancelled_at if cancellation else None
        await self._session.flush()

    async def next_number(self, year: int) -> int:
        statement = (
            insert(EventCounterRow)
            .values(year=year, last=1)
            .on_conflict_do_update(
                index_elements=[EventCounterRow.year],
                set_={"last": EventCounterRow.last + 1},
            )
            .returning(EventCounterRow.last)
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def search(
        self, filters: EventFilters, *, limit: int, offset: int
    ) -> tuple[list[EventSummary], int]:
        conditions = _conditions(filters)
        rows = await self._session.execute(
            select(EventRow, ClientRow.name)
            .join(ClientRow, ClientRow.id == EventRow.client_id)
            .where(*conditions)
            .order_by(EventRow.event_date, EventRow.start_time, EventRow.code)
            .limit(limit)
            .offset(offset)
        )
        total = await self._session.scalar(
            select(func.count())
            .select_from(EventRow)
            .join(ClientRow, ClientRow.id == EventRow.client_id)
            .where(*conditions)
        )
        items = [
            EventSummary(
                id=row.id,
                code=row.code,
                contract_id=row.contract_id,
                client_name=client_name,
                event_type=EventType(row.event_type),
                event_date=row.event_date,
                start_time=row.start_time,
                end_time=row.end_time,
                venue=row.venue,
                guests=row.guests,
                coordinator_id=row.coordinator_id,
                status=EventStatus(row.status),
            )
            for row, client_name in rows
        ]
        return items, int(total or 0)

    async def _to_event(self, row: EventRow) -> Event:
        services = await self._session.scalars(
            select(EventServiceRow)
            .where(EventServiceRow.event_id == row.id)
            .order_by(EventServiceRow.position)
        )
        return Event(
            id=row.id,
            code=row.code,
            contract_id=row.contract_id,
            quote_id=row.quote_id,
            client_id=row.client_id,
            event_type=EventType(row.event_type),
            event_date=row.event_date,
            start_time=row.start_time,
            end_time=row.end_time,
            venue=row.venue,
            guests=row.guests,
            coordinator_id=row.coordinator_id,
            status=EventStatus(row.status),
            services=tuple(
                EventService(
                    kind=LineKind(s.kind),
                    service_id=s.service_id,
                    description=s.description,
                    unit=LineUnit(s.price_unit),
                    quantity=s.quantity,
                )
                for s in services
            ),
            created_by=row.created_by,
            created_at=row.created_at,
            cancellation=_cancellation(row),
        )


def _cancellation(row: EventRow) -> EventCancellation | None:
    if row.cancel_reason is None:
        return None
    assert row.cancelled_by is not None and row.cancelled_at is not None
    return EventCancellation(
        reason=row.cancel_reason, cancelled_by=row.cancelled_by, cancelled_at=row.cancelled_at
    )


def _conditions(filters: EventFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.text:
        name = func.translate(func.lower(ClientRow.name), WITH_ACCENTS, WITHOUT_ACCENTS)
        conditions.append(
            or_(
                EventRow.code.icontains(filters.text, autoescape=True),
                name.contains(normalize(filters.text), autoescape=True),
            )
        )
    if filters.status is not None:
        conditions.append(EventRow.status == filters.status.value)
    if filters.date_from is not None:
        conditions.append(EventRow.event_date >= filters.date_from)
    if filters.date_to is not None:
        conditions.append(EventRow.event_date <= filters.date_to)
    return conditions
