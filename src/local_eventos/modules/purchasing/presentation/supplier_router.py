"""Endpoints de proveedores (HU27). Exigen `purchasing:manage`."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from local_eventos.modules.identity.public_api import Permission, require_permission
from local_eventos.modules.purchasing.application.use_cases.suppliers import (
    CreateSupplier,
    GetSupplier,
    ListSuppliers,
    SetSupplierActive,
    SupplierCommand,
    UpdateSupplier,
)
from local_eventos.modules.purchasing.presentation.dependencies import Suppliers
from local_eventos.modules.purchasing.presentation.schemas import SupplierIn, SupplierOut
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/purchasing/suppliers",
    tags=["compras"],
    dependencies=[Depends(require_permission(Permission.PURCHASING_MANAGE))],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

_Responses = dict[int | str, dict[str, Any]]
_NOT_FOUND: _Responses = {404: {"model": Problem, "description": "`purchasing.supplier_not_found`"}}
_SAVE: _Responses = {
    409: {"model": Problem, "description": "`purchasing.document_taken`"},
    422: {"model": Problem, "description": "`purchasing.validation`"},
}


def _command(body: SupplierIn) -> SupplierCommand:
    return SupplierCommand(**body.model_dump())


@router.get("", operation_id="purchasing_suppliers_list")
async def list_suppliers(
    suppliers: Suppliers,
    text: Annotated[str, Query(description="Parte de la razón social o del documento")] = "",
    include_inactive: bool = False,
) -> list[SupplierOut]:
    """CA-27.2: sin distinguir mayúsculas ni tildes, ordenados por razón social."""
    found = await ListSuppliers(suppliers)(text, include_inactive=include_inactive)
    return [SupplierOut.from_supplier(s) for s in found]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    operation_id="purchasing_suppliers_create",
    responses=_SAVE,
)
async def create_supplier(body: SupplierIn, suppliers: Suppliers) -> SupplierOut:
    return SupplierOut.from_supplier(await CreateSupplier(suppliers)(_command(body)))


@router.get("/{supplier_id}", operation_id="purchasing_suppliers_get", responses=_NOT_FOUND)
async def get_supplier(supplier_id: UUID, suppliers: Suppliers) -> SupplierOut:
    return SupplierOut.from_supplier(await GetSupplier(suppliers)(supplier_id))


@router.put(
    "/{supplier_id}",
    operation_id="purchasing_suppliers_update",
    responses={**_SAVE, **_NOT_FOUND},
)
async def update_supplier(supplier_id: UUID, body: SupplierIn, suppliers: Suppliers) -> SupplierOut:
    return SupplierOut.from_supplier(await UpdateSupplier(suppliers)(supplier_id, _command(body)))


@router.post(
    "/{supplier_id}/deactivate",
    operation_id="purchasing_suppliers_deactivate",
    responses=_NOT_FOUND,
)
async def deactivate_supplier(supplier_id: UUID, suppliers: Suppliers) -> SupplierOut:
    """CA-27.3: no se elimina; se desactiva y deja de recibir órdenes."""
    supplier = await SetSupplierActive(suppliers)(supplier_id, active=False)
    return SupplierOut.from_supplier(supplier)


@router.post(
    "/{supplier_id}/activate", operation_id="purchasing_suppliers_activate", responses=_NOT_FOUND
)
async def activate_supplier(supplier_id: UUID, suppliers: Suppliers) -> SupplierOut:
    return SupplierOut.from_supplier(await SetSupplierActive(suppliers)(supplier_id, active=True))
