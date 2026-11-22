"""Puerto: historial de accesos (HU03). Solo se agregan registros, nunca se cambian."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from local_eventos.modules.identity.domain.access_attempt import AccessAttempt, AccessResult


@dataclass(frozen=True)
class AccessLogEntry:
    id: int
    email: str
    user_id: UUID | None
    user_name: str | None
    result: AccessResult
    occurred_at: datetime


@dataclass(frozen=True)
class AccessLogFilter:
    user_id: UUID | None = None
    since: datetime | None = None
    until: datetime | None = None
    result: AccessResult | None = None


class AccessLogRepository(Protocol):
    async def add(self, attempt: AccessAttempt) -> None: ...

    async def search(
        self, filters: AccessLogFilter, *, limit: int, offset: int
    ) -> tuple[list[AccessLogEntry], int]:
        """Devuelve una página, del más reciente al más antiguo, y el total que cumple el filtro."""
        ...
