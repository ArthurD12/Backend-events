"""Caso de uso: consultar el historial del asistente con filtros, paginado y valoración (HU40).

Lo usan el administrador (todas las consultas) y cada usuario (solo las suyas, con `user_id`)."""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.assistant.application.ports.feedback_log import FeedbackLog
from local_eventos.modules.assistant.application.ports.query_log import QueryFilter, QueryLog
from local_eventos.modules.assistant.domain.feedback import Feedback
from local_eventos.modules.assistant.domain.query_record import QueryRecord

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class QueryPage:
    items: list[QueryRecord]
    feedback: dict[UUID, Feedback]  # la última valoración de cada consulta que la tiene
    total: int
    page: int
    page_size: int


class SearchQueries:
    def __init__(self, log: QueryLog, feedback: FeedbackLog) -> None:
        self._log = log
        self._feedback = feedback

    async def __call__(
        self, filters: QueryFilter, *, page: int = 1, page_size: int = 50
    ) -> QueryPage:
        page = max(page, 1)
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        items, total = await self._log.search(
            filters, limit=page_size, offset=(page - 1) * page_size
        )
        feedback = await self._feedback.latest([r.id for r in items])
        return QueryPage(
            items=items, feedback=feedback, total=total, page=page, page_size=page_size
        )
