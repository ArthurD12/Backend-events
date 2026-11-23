"""Endpoints de servicios del catálogo (HU06). Traducen HTTP ⇄ caso de uso; sin reglas de negocio.

El precio es referencial: la cotización lo copia y lo congela (AGENTS.md, regla 6).
Leer exige `catalog:read` (los tres roles); registrar y modificar, `catalog:manage` (solo el
administrador), según DOMAIN.md §9.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from local_eventos.modules.catalog.application.use_cases.change_service_status import (
    ActivateService,
    DeactivateService,
)
from local_eventos.modules.catalog.application.use_cases.register_service import (
    RegisterService,
    RegisterServiceCommand,
)
from local_eventos.modules.catalog.application.use_cases.search_services import (
    SearchServices,
    SearchServicesQuery,
)
from local_eventos.modules.catalog.application.use_cases.update_service import (
    UpdateService,
    UpdateServiceCommand,
)
from local_eventos.modules.catalog.presentation.catalog_schemas import ServiceIn, ServiceOut
from local_eventos.modules.catalog.presentation.dependencies import Categories, Services
from local_eventos.modules.identity.public_api import Permission, require_permission
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/catalog/services",
    tags=["catálogo"],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

_READ = [Depends(require_permission(Permission.CATALOG_READ))]
_MANAGE = [Depends(require_permission(Permission.CATALOG_MANAGE))]

_Responses = dict[int | str, dict[str, Any]]

_SERVICE_NOT_FOUND: _Responses = {
    404: {"model": Problem, "description": "`catalog.service_not_found`"}
}
_CATEGORY_PROBLEMS: _Responses = {
    404: {"model": Problem, "description": "`catalog.category_not_found`"},
    409: {"model": Problem, "description": "`catalog.category_inactive`"},
    422: {"model": Problem, "description": "Dato inválido: `catalog.price_invalid`, etc."},
}


@router.post(
    "",
    dependencies=_MANAGE,
    status_code=status.HTTP_201_CREATED,
    operation_id="catalog_services_register",
    responses=_CATEGORY_PROBLEMS,
)
async def register_service(
    body: ServiceIn, services: Services, categories: Categories
) -> ServiceOut:
    """Registra un servicio activo en una categoría activa."""
    service = await RegisterService(services, categories)(
        RegisterServiceCommand(
            name=body.name,
            category_id=body.category_id,
            price_unit=body.price_unit,
            reference_price_cents=body.reference_price_cents,
            description=body.description,
        )
    )
    return ServiceOut.from_service(service)


@router.get("", dependencies=_READ, operation_id="catalog_services_search")
async def search_services(
    services: Services,
    text: Annotated[str, Query(description="Parte del nombre del servicio")] = "",
    category_id: UUID | None = None,
    include_inactive: bool = False,
) -> list[ServiceOut]:
    """Busca por nombre (sin distinguir mayúsculas) y categoría. Máximo 50, ordenados."""
    found = await SearchServices(services)(
        SearchServicesQuery(
            text=text, category_id=category_id, active=None if include_inactive else True
        )
    )
    return [ServiceOut.from_service(service) for service in found]


@router.put(
    "/{service_id}",
    dependencies=_MANAGE,
    operation_id="catalog_services_update",
    responses={**_CATEGORY_PROBLEMS, **_SERVICE_NOT_FOUND},
)
async def update_service(
    service_id: UUID, body: ServiceIn, services: Services, categories: Categories
) -> ServiceOut:
    """Modifica el servicio. Las cotizaciones ya hechas no cambian: guardan su copia del precio."""
    service = await UpdateService(services, categories)(
        UpdateServiceCommand(
            service_id=service_id,
            name=body.name,
            category_id=body.category_id,
            price_unit=body.price_unit,
            reference_price_cents=body.reference_price_cents,
            description=body.description,
        )
    )
    return ServiceOut.from_service(service)


@router.post(
    "/{service_id}/deactivate",
    dependencies=_MANAGE,
    operation_id="catalog_services_deactivate",
    responses=_SERVICE_NOT_FOUND,
)
async def deactivate_service(service_id: UUID, services: Services) -> ServiceOut:
    """Desactiva sin eliminar: deja de ofrecerse en cotizaciones nuevas (RN02)."""
    return ServiceOut.from_service(await DeactivateService(services)(service_id))


@router.post(
    "/{service_id}/activate",
    dependencies=_MANAGE,
    operation_id="catalog_services_activate",
    responses=_SERVICE_NOT_FOUND,
)
async def activate_service(service_id: UUID, services: Services) -> ServiceOut:
    """Vuelve a ofrecer un servicio desactivado."""
    return ServiceOut.from_service(await ActivateService(services)(service_id))
