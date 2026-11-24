"""Contratos en memoria para probar los casos de uso sin base de datos."""

from dataclasses import replace
from uuid import UUID

from local_eventos.modules.commercial.application.clients.search_text import normalize
from local_eventos.modules.commercial.application.contracts.errors import (
    ContractAlreadyExistsError,
)
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractFilters,
    ContractSummary,
)
from local_eventos.modules.commercial.domain.contracts.contract import Contract


class InMemoryContractRepository:
    def __init__(self, client_names: dict[UUID, str] | None = None) -> None:
        self.contracts: dict[UUID, Contract] = {}
        self.counters: dict[int, int] = {}
        self._client_names = client_names or {}

    async def get(self, contract_id: UUID) -> Contract | None:
        contract = self.contracts.get(contract_id)
        return replace(contract) if contract else None

    async def get_by_quote(self, quote_id: UUID) -> Contract | None:
        return next((replace(c) for c in self.contracts.values() if c.quote_id == quote_id), None)

    async def add(self, contract: Contract) -> None:
        if any(c.quote_id == contract.quote_id for c in self.contracts.values()):
            raise ContractAlreadyExistsError()
        self.contracts[contract.id] = replace(contract)

    async def update(self, contract: Contract) -> None:
        self.contracts[contract.id] = replace(contract)

    async def next_number(self, year: int) -> int:
        self.counters[year] = self.counters.get(year, 0) + 1
        return self.counters[year]

    async def search(
        self, filters: ContractFilters, *, limit: int, offset: int
    ) -> tuple[list[ContractSummary], int]:
        text = normalize(filters.text)
        found = [
            ContractSummary(
                id=c.id,
                code=c.code,
                quote_id=c.quote_id,
                client_name=self._client_names.get(c.client_id, ""),
                event_date=c.event_date,
                total_cents=c.total_cents,
                advance_cents=c.advance_cents,
                status=c.status,
            )
            for c in sorted(self.contracts.values(), key=lambda c: c.created_at, reverse=True)
        ]
        found = [
            s
            for s in found
            if (not text or text in s.code.lower() or text in normalize(s.client_name))
            and (filters.status is None or s.status is filters.status)
            and (filters.client_id is None or self.contracts[s.id].client_id == filters.client_id)
        ]
        return found[offset : offset + limit], len(found)
