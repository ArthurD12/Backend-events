"""Puerto del repositorio de contratos: la aplicación lo usa, la infraestructura lo cumple."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from local_eventos.modules.commercial.domain.contracts.contract import Contract, ContractStatus


@dataclass(frozen=True)
class ContractFilters:
    text: str = ""  # parte del código o del nombre del cliente
    status: ContractStatus | None = None
    client_id: UUID | None = None


@dataclass(frozen=True)
class ContractSummary:
    id: UUID
    code: str
    quote_id: UUID
    client_name: str
    event_date: date
    total_cents: int
    advance_cents: int
    status: ContractStatus


class ContractRepository(Protocol):
    async def get(self, contract_id: UUID) -> Contract | None: ...

    async def get_by_quote(self, quote_id: UUID) -> Contract | None: ...

    async def add(self, contract: Contract) -> None:
        """Si la cotización ya tiene contrato, lanza `ContractAlreadyExistsError`."""
        ...

    async def update(self, contract: Contract) -> None: ...

    async def next_number(self, year: int) -> int: ...

    async def search(
        self, filters: ContractFilters, *, limit: int, offset: int
    ) -> tuple[list[ContractSummary], int]:
        """Una página, del más reciente al más antiguo, y el total que cumple el filtro."""
        ...
