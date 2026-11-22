"""Pagos en memoria para probar sin base de datos."""

from uuid import UUID

from local_eventos.modules.ledger.domain.payment import Payment


class InMemoryPaymentRepository:
    def __init__(self) -> None:
        self.payments: list[Payment] = []

    async def add(self, payment: Payment) -> None:
        self.payments.append(payment)

    async def list_for_contract(self, contract_id: UUID) -> list[Payment]:
        return [p for p in self.payments if p.contract_id == contract_id]
