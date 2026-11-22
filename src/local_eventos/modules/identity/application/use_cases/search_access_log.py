"""Caso de uso: consultar el historial de accesos con filtros y paginado (HU03)."""

from dataclasses import dataclass

from local_eventos.modules.identity.application.ports.access_log_repository import (
    AccessLogEntry,
    AccessLogFilter,
    AccessLogRepository,
)

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class AccessLogPage:
    items: list[AccessLogEntry]
    total: int
    page: int
    page_size: int


class SearchAccessLog:
    def __init__(self, access_log: AccessLogRepository) -> None:
        self._access_log = access_log

    async def __call__(
        self, filters: AccessLogFilter, *, page: int = 1, page_size: int = 50
    ) -> AccessLogPage:
        page = max(page, 1)
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        items, total = await self._access_log.search(
            filters, limit=page_size, offset=(page - 1) * page_size
        )
        return AccessLogPage(items=items, total=total, page=page, page_size=page_size)
