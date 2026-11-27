"""Caso de uso: el autor de una consulta valora la respuesta como correcta o incorrecta (HU40)."""

from uuid import UUID

from local_eventos.modules.assistant.application.errors import QueryNotFoundError
from local_eventos.modules.assistant.application.ports.feedback_log import FeedbackLog
from local_eventos.modules.assistant.application.ports.query_log import Clock, QueryLog
from local_eventos.modules.assistant.domain.feedback import (
    MAX_COMMENT_LENGTH,
    Feedback,
    FeedbackValue,
)


class RateQuery:
    def __init__(self, queries: QueryLog, feedback: FeedbackLog, clock: Clock) -> None:
        self._queries = queries
        self._feedback = feedback
        self._clock = clock

    async def __call__(
        self, user_id: UUID, query_id: UUID, value: FeedbackValue, comment: str | None = None
    ) -> Feedback:
        """Solo el autor valora; otra persona recibe "no existe" (no se revela la consulta).

        Valorar de nuevo agrega una fila: la vigente es la última (R-IA-8).
        """
        query = await self._queries.get(query_id)
        if query is None or query.user_id != user_id:
            raise QueryNotFoundError()
        clean = " ".join((comment or "").split())[:MAX_COMMENT_LENGTH] or None
        feedback = Feedback(query_id, user_id, value, clean, self._clock.now())
        await self._feedback.add(feedback)
        return feedback
