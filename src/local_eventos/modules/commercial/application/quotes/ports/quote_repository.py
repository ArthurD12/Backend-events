"""Puerto del repositorio de cotizaciones: la aplicación lo usa, la infraestructura lo cumple."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from local_eventos.modules.commercial.domain.quotes.quote import EventType, Quote, QuoteStatus


@dataclass(frozen=True)
class QuoteFilters:
    text: str = ""  # parte del código o del nombre del cliente
    client_id: UUID | None = None
    status: QuoteStatus | None = None  # EXPIRED también se puede buscar
    event_date_from: date | None = None
    event_date_to: date | None = None


@dataclass(frozen=True)
class QuoteSummary:
    """Fila de la lista de cotizaciones (sin las líneas)."""

    id: UUID
    code: str
    client_id: UUID
    client_name: str
    event_type: EventType
    event_date: date
    guests: int
    total_cents: int
    status: QuoteStatus  # el efectivo: incluye EXPIRED
    valid_until: date


class QuoteRepository(Protocol):
    async def get(self, quote_id: UUID) -> Quote | None: ...

    async def add(self, quote: Quote) -> None: ...

    async def update(self, quote: Quote) -> None: ...

    async def next_number(self, year: int) -> int:
        """Siguiente correlativo del año. Dos llamadas simultáneas nunca reciben el mismo."""
        ...

    async def search(
        self, filters: QuoteFilters, *, today: date, limit: int, offset: int
    ) -> tuple[list[QuoteSummary], int]:
        """Una página, de la más reciente a la más antigua, y el total que cumple el filtro."""
        ...
