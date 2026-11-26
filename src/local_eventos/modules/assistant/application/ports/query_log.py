"""Puerto del registro de consultas (solo inserción) y del reloj."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from local_eventos.modules.assistant.domain.query_record import QueryRecord


@dataclass(frozen=True)
class QueryFilter:
    user_id: UUID | None = None
    since: datetime | None = None
    until: datetime | None = None


class QueryLog(Protocol):
    async def add(self, record: QueryRecord) -> None: ...

    async def count_since(self, user_id: UUID, since: datetime) -> int:
        """Consultas del usuario desde `since` (límite por hora, R-IA-2)."""
        ...

    async def search(
        self, filters: QueryFilter, *, limit: int, offset: int
    ) -> tuple[list[QueryRecord], int]:
        """Una página, de la más reciente a la más antigua, y el total que cumple el filtro."""
        ...


class Clock(Protocol):
    def now(self) -> datetime:
        """Instante actual en UTC."""
        ...
