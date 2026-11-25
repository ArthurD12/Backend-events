"""Consulta para `reporting`: lo contratado y cobrado de un evento (HU22, CA-22.3).

`commercial` sabe qué contrato tiene el evento y cómo se calcula su saldo (RN15); `reporting`
lo junta con los egresos del evento que guarda `ledger`.
"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from local_eventos.modules.commercial.application.clients.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractRepository,
)
from local_eventos.modules.commercial.application.contracts.use_cases.payments import balance_of
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventRepository,
)
from local_eventos.modules.ledger.public_api import PaymentEntriesLookup


@dataclass(frozen=True)
class EventFinance:
    event_id: UUID
    event_code: str
    event_date: date
    event_status: str
    client_name: str
    contract_id: UUID
    contract_code: str
    total_cents: int
    paid_cents: int
    refunded_cents: int
    balance_cents: int


class GetEventFinance:
    def __init__(
        self,
        events: EventRepository,
        contracts: ContractRepository,
        clients: ClientRepository,
        entries: PaymentEntriesLookup,
    ) -> None:
        self._events = events
        self._contracts = contracts
        self._clients = clients
        self._entries = entries

    async def __call__(self, event_id: UUID) -> EventFinance | None:
        event = await self._events.get(event_id)
        if event is None:
            return None
        contract = await self._contracts.get(event.contract_id)
        if contract is None:  # la base lo impide con una FK; solo por si acaso
            return None
        client = await self._clients.get(event.client_id)
        balance = balance_of(contract, await self._entries(contract.id))
        return EventFinance(
            event_id=event.id,
            event_code=event.code,
            event_date=event.event_date,
            event_status=event.status.value,
            client_name=client.name if client else "",
            contract_id=contract.id,
            contract_code=contract.code,
            total_cents=balance.total_cents,
            paid_cents=balance.paid_cents,
            refunded_cents=balance.refunded_cents,
            balance_cents=balance.balance_cents,
        )
