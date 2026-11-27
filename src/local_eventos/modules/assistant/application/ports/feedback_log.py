"""Puerto del registro de valoraciones (solo inserción)."""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.assistant.domain.feedback import Feedback


class FeedbackLog(Protocol):
    async def add(self, feedback: Feedback) -> None: ...

    async def latest(self, query_ids: list[UUID]) -> dict[UUID, Feedback]:
        """La última valoración de cada consulta (las que no tienen, no aparecen)."""
        ...
