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

    async def get_for_update(self, contract_id: UUID) -> Contract | None:
        """Lee y bloquea la fila hasta el fin de la transacción (`SELECT … FOR UPDATE`): dos
        pagos simultáneos al mismo contrato se registran uno tras otro."""
        ...

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

    async def get_many(self, contract_ids: list[UUID]) -> list[Contract]:
        """Los que existan, en cualquier orden (reportes)."""
        ...

    async def list_by_status(self, status: ContractStatus) -> list[Contract]:
        """Todos los contratos en ese estado (p. ej., firmados para los cobros pendientes)."""
        ...
