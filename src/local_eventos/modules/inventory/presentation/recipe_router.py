"""Endpoints de recetas (HU24): los insumos de cada servicio del catálogo.

Ver exige `inventory:read`; guardar, `inventory:manage`.
"""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends

from local_eventos.modules.identity.public_api import Permission, require_permission
from local_eventos.modules.inventory.application.use_cases.recipes import GetRecipe, PutRecipe
from local_eventos.modules.inventory.domain.recipe import RecipeLine
from local_eventos.modules.inventory.presentation.dependencies import Products, Recipes, Services
from local_eventos.modules.inventory.presentation.schemas import RecipeIn, RecipeOut
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/inventory",
    tags=["almacén"],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

_NOT_FOUND = "`inventory.service_not_found`"


@router.get(
    "/recipes/{service_id}",
    dependencies=[Depends(require_permission(Permission.INVENTORY_READ))],
    operation_id="inventory_recipe_get",
    responses={404: {"model": Problem, "description": _NOT_FOUND}},
)
async def get_recipe(
    service_id: UUID, recipes: Recipes, products: Products, services: Services
) -> RecipeOut:
    """CA-24.1: insumos del servicio (vacío si aún no tiene)."""
    return RecipeOut.from_view(await GetRecipe(recipes, products, services)(service_id))


@router.put(
    "/recipes/{service_id}",
    dependencies=[Depends(require_permission(Permission.INVENTORY_MANAGE))],
    operation_id="inventory_recipe_put",
    responses={
        404: {
            "model": Problem,
            "description": f"{_NOT_FOUND}, `inventory.product_not_found`",
        },
        422: {"model": Problem, "description": "`inventory.validation`"},
    },
)
async def put_recipe(
    service_id: UUID, body: RecipeIn, recipes: Recipes, products: Products, services: Services
) -> RecipeOut:
    """CA-24.3: reemplaza todos los insumos del servicio; un producto una sola vez (CA-24.2)."""
    lines = [RecipeLine(item.product_id, Decimal(item.quantity), item.basis) for item in body.lines]
    return RecipeOut.from_view(await PutRecipe(recipes, products, services)(service_id, lines))
