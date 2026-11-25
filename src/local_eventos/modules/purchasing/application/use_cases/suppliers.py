"""Casos de uso de proveedores (HU27): registrar, modificar, activar y buscar."""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.purchasing.application.errors import (
    DocumentTakenError,
    SupplierNotFoundError,
)
from local_eventos.modules.purchasing.application.ports.repositories import SupplierRepository
from local_eventos.modules.purchasing.domain.supplier import DocumentType, Supplier

MAX_RESULTS = 100


@dataclass(frozen=True)
class SupplierCommand:
    name: str
    document_type: DocumentType
    document_number: str
    phone: str
    contact_name: str | None = None
    email: str | None = None
    address: str | None = None


class CreateSupplier:
    def __init__(self, suppliers: SupplierRepository) -> None:
        self._suppliers = suppliers

    async def __call__(self, command: SupplierCommand) -> Supplier:
        supplier = Supplier.register(
            name=command.name,
            document_type=command.document_type,
            document_number=command.document_number,
            phone=command.phone,
            contact_name=command.contact_name,
            email=command.email,
            address=command.address,
        )
        if await self._suppliers.get_by_document(supplier.document_type, supplier.document_number):
            raise DocumentTakenError()
        await self._suppliers.add(supplier)
        return supplier


class UpdateSupplier:
    def __init__(self, suppliers: SupplierRepository) -> None:
        self._suppliers = suppliers

    async def __call__(self, supplier_id: UUID, command: SupplierCommand) -> Supplier:
        supplier = await GetSupplier(self._suppliers)(supplier_id)
        supplier.update(
            name=command.name,
            document_type=command.document_type,
            document_number=command.document_number,
            phone=command.phone,
            contact_name=command.contact_name,
            email=command.email,
            address=command.address,
        )
        same = await self._suppliers.get_by_document(
            supplier.document_type, supplier.document_number
        )
        if same is not None and same.id != supplier.id:
            raise DocumentTakenError()
        await self._suppliers.update(supplier)
        return supplier


class SetSupplierActive:
    """CA-27.3: no se elimina; se desactiva y se puede volver a activar."""

    def __init__(self, suppliers: SupplierRepository) -> None:
        self._suppliers = suppliers

    async def __call__(self, supplier_id: UUID, *, active: bool) -> Supplier:
        supplier = await GetSupplier(self._suppliers)(supplier_id)
        if active:
            supplier.activate()
        else:
            supplier.deactivate()
        await self._suppliers.update(supplier)
        return supplier


class GetSupplier:
    def __init__(self, suppliers: SupplierRepository) -> None:
        self._suppliers = suppliers

    async def __call__(self, supplier_id: UUID) -> Supplier:
        supplier = await self._suppliers.get(supplier_id)
        if supplier is None:
            raise SupplierNotFoundError()
        return supplier


class ListSuppliers:
    def __init__(self, suppliers: SupplierRepository) -> None:
        self._suppliers = suppliers

    async def __call__(self, text: str = "", *, include_inactive: bool = False) -> list[Supplier]:
        """CA-27.2: por razón social o documento, sin distinguir tildes."""
        return await self._suppliers.search(
            " ".join(text.split()), include_inactive=include_inactive, limit=MAX_RESULTS
        )
