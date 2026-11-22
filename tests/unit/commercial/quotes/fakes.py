"""Piezas falsas para probar los casos de uso de cotizaciones sin base de datos."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from local_eventos.modules.catalog.public_api import ServiceSummary
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteFilters,
    QuoteSummary,
)
from local_eventos.modules.commercial.domain.quotes.quote import Quote


class InMemoryQuoteRepository:
    def __init__(self, client_names: dict[UUID, str] | None = None) -> None:
        self.quotes: dict[UUID, Quote] = {}
        self.counters: dict[int, int] = {}
        self._client_names = client_names or {}

    async def get(self, quote_id: UUID) -> Quote | None:
        quote = self.quotes.get(quote_id)
        return replace(quote) if quote else None

    async def add(self, quote: Quote) -> None:
        self.quotes[quote.id] = replace(quote)

    async def update(self, quote: Quote) -> None:
        self.quotes[quote.id] = replace(quote)

    async def next_number(self, year: int) -> int:
        self.counters[year] = self.counters.get(year, 0) + 1
        return self.counters[year]

    async def search(
        self, filters: QuoteFilters, *, today: date, limit: int, offset: int
    ) -> tuple[list[QuoteSummary], int]:
        text = filters.text.lower()
        found = [
            QuoteSummary(
                id=q.id,
                code=q.code,
                client_id=q.client_id,
                client_name=self._client_names.get(q.client_id, ""),
                event_type=q.details.event_type,
                event_date=q.details.event_date,
                guests=q.details.guests,
                total_cents=q.total_cents,
                status=q.effective_status(today),
                valid_until=q.valid_until,
            )
            for q in sorted(self.quotes.values(), key=lambda q: q.created_at, reverse=True)
        ]
        found = [
            s
            for s in found
            if (not text or text in s.code.lower() or text in s.client_name.lower())
            and (filters.client_id is None or s.client_id == filters.client_id)
            and (filters.status is None or s.status is filters.status)
            and (filters.event_date_from is None or s.event_date >= filters.event_date_from)
            and (filters.event_date_to is None or s.event_date <= filters.event_date_to)
        ]
        return found[offset : offset + limit], len(found)


class FakeServiceLookup:
    """Catálogo falso: se puede cambiar el precio o desactivar un servicio en medio de la prueba."""

    def __init__(self) -> None:
        self.services: dict[UUID, ServiceSummary] = {}

    def add(self, name: str, unit: str, price: int, *, active: bool = True) -> UUID:
        service_id = uuid4()
        self.services[service_id] = ServiceSummary(
            id=service_id,
            name=name,
            category_id=uuid4(),
            price_unit=unit,
            reference_price_cents=price,
            currency="PEN",
            active=active,
        )
        return service_id

    def change(self, service_id: UUID, **changes: object) -> None:
        self.services[service_id] = replace(self.services[service_id], **changes)  # type: ignore[arg-type]

    async def __call__(self, service_id: UUID) -> ServiceSummary | None:
        return self.services.get(service_id)


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 11, 22, 15, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def today(self) -> date:
        return (self.current - timedelta(hours=5)).date()

    def advance(self, **delta: float) -> None:
        self.current += timedelta(**delta)
