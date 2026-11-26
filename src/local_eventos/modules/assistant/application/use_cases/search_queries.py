"""Caso de uso: consultar el historial del asistente con filtros y paginado (HU40)."""

from dataclasses import dataclass

from local_eventos.modules.assistant.application.ports.query_log import QueryFilter, QueryLog
from local_eventos.modules.assistant.domain.query_record import QueryRecord

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class QueryPage:
    items: list[QueryRecord]
    total: int
    page: int
    page_size: int


class SearchQueries:
    def __init__(self, log: QueryLog) -> None:
        self._log = log

    async def __call__(
        self, filters: QueryFilter, *, page: int = 1, page_size: int = 50
    ) -> QueryPage:
        page = max(page, 1)
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        items, total = await self._log.search(
            filters, limit=page_size, offset=(page - 1) * page_size
        )
        return QueryPage(items=items, total=total, page=page, page_size=page_size)
