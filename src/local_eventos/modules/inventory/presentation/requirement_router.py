"""Requerimiento de materiales del evento (HU25) y sus reservas. Ver exige `inventory:read`."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from local_eventos.modules.identity.public_api import CurrentUser, Permission, require_permission
from local_eventos.modules.inventory.application.errors import EventNotFoundError
from local_eventos.modules.inventory.application.use_cases.requirement import (
    GetEventRequirement,
)
from local_eventos.modules.inventory.application.use_cases.reservations import (
    ReleaseReservation,
    ReserveMaterials,
)
from local_eventos.modules.inventory.presentation.dependencies import (
    EventDetails,
    Events,
    Movements,
    Products,
    Recipes,
    Reservations,
    Stock,
    Today,
)
from local_eventos.modules.inventory.presentation.schemas import (
    EventRequirementOut,
    ReservationOut,
    ReservationsIn,
)
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


Manager = Annotated[CurrentUser, Depends(require_permission(Permission.INVENTORY_MANAGE))]


@router.post(
    "/events/{event_id}/reservations",
    status_code=status.HTTP_201_CREATED,
    operation_id="inventory_reservations_create",
    responses={
        404: {
            "model": Problem,
            "description": "`inventory.event_not_found`, `inventory.product_not_found`",
        },
        409: {
            "model": Problem,
            "description": "`inventory.insufficient_available`, `inventory.event_not_assignable`,"
            " `inventory.product_inactive`",
        },
        422: {"model": Problem, "description": "`inventory.validation`"},
    },
)
async def create_reservations(
    event_id: UUID,
    body: ReservationsIn,
    user: Manager,
    products: Products,
    stock: Stock,
    reservations: Reservations,
    events: Events,
    clock: Today,
) -> list[ReservationOut]:
    """CA-25.4: aparta lo disponible para el evento sin mover el stock (R-REC-3).

    Devuelve todo lo vigente reservado del evento.
    """
    lines = await ReserveMaterials(products, stock, reservations, events, clock)(
        event_id, [(item.product_id, Decimal(item.quantity)) for item in body.lines], by=user.id
    )
    return [ReservationOut.from_line(line) for line in lines]


@router.delete(
    "/events/{event_id}/reservations/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission(Permission.INVENTORY_MANAGE))],
    operation_id="inventory_reservations_delete",
    responses={404: {"model": Problem, "description": "`inventory.reservation_not_found`"}},
)
async def delete_reservation(
    event_id: UUID, product_id: UUID, stock: Stock, reservations: Reservations, clock: Today
) -> Response:
    """Libera la reserva vigente del producto en el evento."""
    await ReleaseReservation(reservations, stock, clock)(event_id, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
