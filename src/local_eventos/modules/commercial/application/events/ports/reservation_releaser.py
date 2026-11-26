"""Puerto para liberar los materiales reservados de un evento (R-REC-3).

Lo implementa `inventory` y lo conecta `commercial.presentation` con
`inventory.public_api`: así `commercial.application` no depende de `inventory`.
"""

from typing import Protocol
from uuid import UUID


class ReservationReleaser(Protocol):
    async def __call__(self, event_id: UUID) -> None: ...
