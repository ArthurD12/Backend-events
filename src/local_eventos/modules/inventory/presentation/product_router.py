"""Endpoints de productos del almacén (HU23). Traducen HTTP ⇄ caso de uso; sin reglas de negocio.

Consultar exige `inventory:read` (los tres roles); registrar y modificar, `inventory:manage`
(administrador y encargado de compras y almacén).
"""

from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from local_eventos.modules.identity.public_api import Permission, require_permission
from local_eventos.modules.inventory.application.ports.product_repository import ProductFilters
from local_eventos.modules.inventory.application.use_cases.products import (
    MAX_PAGE_SIZE,
    CreateProduct,
    GetProduct,
    ListProductMovements,
    ListProducts,
    ProductCommand,
    ProductViews,
    SetProductActive,
    UpdateProduct,
)
from local_eventos.modules.inventory.domain.product import Category, Product
from local_eventos.modules.inventory.presentation.dependencies import (
    Movements,
    Products,
    Stock,
    Today,
)
from local_eventos.modules.inventory.presentation.schemas import (
    MovementPageOut,
    ProductIn,
    ProductOut,
)
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/inventory/products",
    tags=["almacén"],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

_READ = [Depends(require_permission(Permission.INVENTORY_READ))]
_MANAGE = [Depends(require_permission(Permission.INVENTORY_MANAGE))]

_Responses = dict[int | str, dict[str, Any]]
_NOT_FOUND: _Responses = {404: {"model": Problem, "description": "`inventory.product_not_found`"}}
_SAVE: _Responses = {
    409: {"model": Problem, "description": "`inventory.code_taken`"},
    422: {"model": Problem, "description": "`inventory.validation`"},
}


def _command(body: ProductIn) -> ProductCommand:
    return ProductCommand(
        code=body.code,
        name=body.name,
        category=body.category,
        unit=body.unit,
        kind=body.kind,
        min_stock=Decimal(body.min_stock),
    )


async def _out(product: Product, stock: Stock, movements: Movements, clock: Today) -> ProductOut:
    return ProductOut.from_view((await ProductViews(stock, movements, clock)([product]))[0])


@router.get("", dependencies=_READ, operation_id="inventory_products_list")
async def list_products(
    products: Products,
    stock: Stock,
    movements: Movements,
    clock: Today,
    text: Annotated[str, Query(description="Parte del código o del nombre, sin tildes")] = "",
    category: Category | None = None,
    include_inactive: bool = False,
    alerts_only: Annotated[bool, Query(description="Solo stock bajo o por vencer")] = False,
) -> list[ProductOut]:
    """Productos con su stock y alertas (CA-23.5), ordenados por nombre."""
    views = await ListProducts(products, ProductViews(stock, movements, clock))(
        ProductFilters(text=text, category=category, include_inactive=include_inactive),
        alerts_only=alerts_only,
    )
    return [ProductOut.from_view(v) for v in views]


@router.post(
    "",
    dependencies=_MANAGE,
    status_code=status.HTTP_201_CREATED,
    operation_id="inventory_products_create",
    responses=_SAVE,
)
async def create_product(
    body: ProductIn, products: Products, stock: Stock, movements: Movements, clock: Today
) -> ProductOut:
    """Registra un producto activo, sin stock: el stock entra con una entrada."""
    product = await CreateProduct(products)(_command(body))
    return await _out(product, stock, movements, clock)


@router.get(
    "/{product_id}", dependencies=_READ, operation_id="inventory_products_get", responses=_NOT_FOUND
)
async def get_product(
    product_id: UUID, products: Products, stock: Stock, movements: Movements, clock: Today
) -> ProductOut:
    view = await GetProduct(products, ProductViews(stock, movements, clock))(product_id)
    return ProductOut.from_view(view)


@router.put(
    "/{product_id}",
    dependencies=_MANAGE,
    operation_id="inventory_products_update",
    responses={**_SAVE, **_NOT_FOUND},
)
async def update_product(
    product_id: UUID,
    body: ProductIn,
    products: Products,
    stock: Stock,
    movements: Movements,
    clock: Today,
) -> ProductOut:
    """Modifica los datos del producto. Su stock y sus movimientos no cambian."""
    product = await UpdateProduct(products)(product_id, _command(body))
    return await _out(product, stock, movements, clock)


@router.post(
    "/{product_id}/deactivate",
    dependencies=_MANAGE,
    operation_id="inventory_products_deactivate",
    responses=_NOT_FOUND,
)
async def deactivate_product(
    product_id: UUID, products: Products, stock: Stock, movements: Movements, clock: Today
) -> ProductOut:
    """CA-23.3: no se elimina; se desactiva y deja de recibir entradas y salidas."""
    product = await SetProductActive(products)(product_id, active=False)
    return await _out(product, stock, movements, clock)


@router.post(
    "/{product_id}/activate",
    dependencies=_MANAGE,
    operation_id="inventory_products_activate",
    responses=_NOT_FOUND,
)
async def activate_product(
    product_id: UUID, products: Products, stock: Stock, movements: Movements, clock: Today
) -> ProductOut:
    product = await SetProductActive(products)(product_id, active=True)
    return await _out(product, stock, movements, clock)


@router.get(
    "/{product_id}/movements",
    dependencies=_READ,
    operation_id="inventory_movements_list",
    responses=_NOT_FOUND,
)
async def list_movements(
    product_id: UUID,
    products: Products,
    movements: Movements,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
) -> MovementPageOut:
    """CA-23.4: historial del producto, del movimiento más reciente al más antiguo."""
    found = await ListProductMovements(products, movements)(
        product_id, page=page, page_size=page_size
    )
    return MovementPageOut.from_page(found)
