"""Requerimiento de materiales del evento (HU25) y sus reservas. Ver exige `inventory:read`."""

from uuid import UUID

from fastapi import APIRouter, Depends

from local_eventos.modules.identity.public_api import Permission, require_permission
from local_eventos.modules.inventory.application.errors import EventNotFoundError
from local_eventos.modules.inventory.application.use_cases.requirement import (
    GetEventRequirement,
)
from local_eventos.modules.inventory.presentation.dependencies import (
    EventDetails,
    Movements,
    Products,
    Recipes,
    Reservations,
    Stock,
)
from local_eventos.modules.inventory.presentation.schemas import EventRequirementOut
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/inventory",
    tags=["almacén"],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)


@router.get(
    "/events/{event_id}/requirement",
    dependencies=[Depends(require_permission(Permission.INVENTORY_READ))],
    operation_id="inventory_event_requirement",
    responses={404: {"model": Problem, "description": "`inventory.event_not_found`"}},
)
async def event_requirement(
    event_id: UUID,
    events: EventDetails,
    recipes: Recipes,
    products: Products,
    stock: Stock,
    movements: Movements,
    reservations: Reservations,
) -> EventRequirementOut:
    """CA-25.1 a CA-25.3: requerido, salido, reservado, disponible y faltante por producto."""
    requirement = await GetEventRequirement(
        events, recipes, products, stock, movements, reservations
    )(event_id)
    if requirement is None:
        raise EventNotFoundError()
    return EventRequirementOut.from_requirement(requirement)
