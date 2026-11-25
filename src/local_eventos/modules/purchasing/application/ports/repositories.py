"""Puertos de los repositorios de proveedores y compras."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from local_eventos.modules.purchasing.domain.purchase import Purchase, PurchaseStatus
from local_eventos.modules.purchasing.domain.supplier import DocumentType, Supplier


class SupplierRepository(Protocol):
    async def get(self, supplier_id: UUID) -> Supplier | None: ...

    async def get_many(self, supplier_ids: list[UUID]) -> list[Supplier]: ...

    async def get_by_document(
        self, document_type: DocumentType, number: str
    ) -> Supplier | None: ...

    async def add(self, supplier: Supplier) -> None:
        """Si el documento ya existe, lanza `DocumentTakenError`."""
        ...

    async def update(self, supplier: Supplier) -> None: ...

    async def search(self, text: str, *, include_inactive: bool, limit: int) -> list[Supplier]:
        """Por razón social o documento, sin distinguir tildes; ordenados por razón social."""
        ...


@dataclass(frozen=True)
class PurchaseFilters:
    status: PurchaseStatus | None = None
    event_id: UUID | None = None
    supplier_id: UUID | None = None


class PurchaseRepository(Protocol):
    async def get(self, purchase_id: UUID, *, for_update: bool = False) -> Purchase | None:
        """Con `for_update`, la compra queda bloqueada hasta el fin de la transacción."""
        ...

    async def add(self, purchase: Purchase) -> None: ...

    async def update(self, purchase: Purchase) -> None: ...

    async def next_number(self, year: int) -> int: ...

    async def search(
        self, filters: PurchaseFilters, *, limit: int, offset: int
    ) -> tuple[list[Purchase], int]:
        """Una página, de la más reciente a la más antigua, y el total."""
        ...
