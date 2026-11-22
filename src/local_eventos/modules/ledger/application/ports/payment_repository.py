"""Puerto: dónde se guardan los pagos. Solo se agregan y se leen, nunca se cambian."""

from typing import Protocol
from uuid import UUID

from local_eventos.modules.ledger.domain.payment import Payment


class PaymentRepository(Protocol):
    async def add(self, payment: Payment) -> None: ...

    async def list_for_contract(self, contract_id: UUID) -> list[Payment]:
        """Pagos del contrato, del más antiguo al más reciente."""
        ...
