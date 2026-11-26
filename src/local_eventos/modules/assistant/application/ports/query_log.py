"""Puerto del registro de consultas (solo inserción) y del reloj."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from local_eventos.modules.assistant.domain.query_record import QueryRecord


class QueryLog(Protocol):
    async def add(self, record: QueryRecord) -> None: ...

    async def count_since(self, user_id: UUID, since: datetime) -> int:
        """Consultas del usuario desde `since` (límite por hora, R-IA-2)."""
        ...


class Clock(Protocol):
    def now(self) -> datetime:
        """Instante actual en UTC."""
        ...
