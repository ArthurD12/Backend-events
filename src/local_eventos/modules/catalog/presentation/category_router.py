"""Endpoints de categorías del catálogo (HU06). Traducen HTTP ⇄ caso de uso; sin reglas de negocio.

Leer exige `catalog:read` (los tres roles); crear y modificar, `catalog:manage` (solo el
administrador), según DOMAIN.md §9.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from local_eventos.modules.catalog.application.use_cases.change_category_status import (
    ActivateCategory,
    DeactivateCategory,
)
from local_eventos.modules.catalog.application.use_cases.create_category import CreateCategory
from local_eventos.modules.catalog.application.use_cases.list_categories import ListCategories
from local_eventos.modules.catalog.application.use_cases.rename_category import RenameCategory
from local_eventos.modules.catalog.presentation.catalog_schemas import CategoryIn, CategoryOut
from local_eventos.modules.catalog.presentation.dependencies import Categories, Services
from local_eventos.modules.identity.public_api import Permission, require_permission
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/catalog/categories",
    tags=["catálogo"],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

_READ = [Depends(require_permission(Permission.CATALOG_READ))]
_MANAGE = [Depends(require_permission(Permission.CATALOG_MANAGE))]

_Responses = dict[int | str, dict[str, Any]]

_NOT_FOUND: _Responses = {404: {"model": Problem, "description": "`catalog.category_not_found`"}}
_DUPLICATED: _Responses = {
    409: {"model": Problem, "description": "`catalog.category_name_duplicated`"}
}
_INVALID: _Responses = {
    422: {"model": Problem, "description": "Dato inválido: `catalog.category_name_required`, etc."}
}


@router.post(
    "",
    dependencies=_MANAGE,
    status_code=status.HTTP_201_CREATED,
    operation_id="catalog_categories_create",
    responses={**_DUPLICATED, **_INVALID},
)
async def create_category(body: CategoryIn, categories: Categories) -> CategoryOut:
    """Crea una categoría activa. El nombre no se repite ("Bebidas" = "bebidas")."""
    return CategoryOut.from_category(await CreateCategory(categories)(body.name))


@router.get("", dependencies=_READ, operation_id="catalog_categories_list")
async def list_categories(
    categories: Categories, include_inactive: bool = False
) -> list[CategoryOut]:
    """Categorías ordenadas por nombre. El formulario de servicios pide solo las activas."""
    found = await ListCategories(categories)(include_inactive=include_inactive)
    return [CategoryOut.from_category(category) for category in found]


@router.put(
    "/{category_id}",
    dependencies=_MANAGE,
    operation_id="catalog_categories_rename",
    responses={**_NOT_FOUND, **_DUPLICATED, **_INVALID},
)
async def rename_category(
    category_id: UUID, body: CategoryIn, categories: Categories
) -> CategoryOut:
    """Cambia el nombre sin repetir el de otra categoría."""
    return CategoryOut.from_category(await RenameCategory(categories)(category_id, body.name))


@router.post(
    "/{category_id}/deactivate",
    dependencies=_MANAGE,
    operation_id="catalog_categories_deactivate",
    responses={
        **_NOT_FOUND,
        409: {"model": Problem, "description": "`catalog.category_has_active_services`"},
    },
)
async def deactivate_category(
    category_id: UUID, categories: Categories, services: Services
) -> CategoryOut:
    """Desactiva sin eliminar. No se puede si la categoría tiene servicios activos."""
    category = await DeactivateCategory(categories, services)(category_id)
    return CategoryOut.from_category(category)


@router.post(
    "/{category_id}/activate",
    dependencies=_MANAGE,
    operation_id="catalog_categories_activate",
    responses=_NOT_FOUND,
)
async def activate_category(category_id: UUID, categories: Categories) -> CategoryOut:
    """Vuelve a activar una categoría desactivada."""
    return CategoryOut.from_category(await ActivateCategory(categories)(category_id))
