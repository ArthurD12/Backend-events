"""Endpoints de ingresos y egresos de caja (HU21). Exigen `payments:record` (administrador y
encargado de eventos); el encargado de compras no ve dinero."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from local_eventos.modules.identity.public_api import CurrentUser, Permission, require_permission
from local_eventos.modules.ledger.application.ports.movement_repository import (
    MovementFilters,
    MovementState,
)
from local_eventos.modules.ledger.application.use_cases.movements import (
    MAX_PAGE_SIZE,
    ListMovements,
    RecordMovement,
    VoidMovement,
)
from local_eventos.modules.ledger.domain.movement import MovementCategory, MovementType
from local_eventos.modules.ledger.presentation.dependencies import Movements, Today, UserNames
from local_eventos.modules.ledger.presentation.movement_schemas import (
    MovementIn,
    MovementOut,
    MovementPageOut,
    MovementVoidIn,
    user_ids,
)
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/movements",
    tags=["caja"],
    dependencies=[Depends(require_permission(Permission.PAYMENTS_RECORD))],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

Cashier = Annotated[CurrentUser, Depends(require_permission(Permission.PAYMENTS_RECORD))]


@router.get("", operation_id="movements_list")
async def list_movements(
    movements: Movements,
    names: UserNames,
    date_from: date | None = None,
    date_to: date | None = None,
    type: MovementType | None = None,  # noqa: A002 - nombre del filtro en la API
    category: MovementCategory | None = None,
    event_id: UUID | None = None,
    state: MovementState | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> MovementPageOut:
    """Movimientos de la fecha más reciente a la más antigua, con filtros (CA-21.4)."""
    found = await ListMovements(movements)(
        MovementFilters(
            date_from=date_from,
            date_to=date_to,
            type=type,
            category=category,
            event_id=event_id,
            state=state,
        ),
        page=page,
        page_size=page_size,
    )
    return MovementPageOut.from_page(found, await names(user_ids(found.items)))


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    operation_id="movements_create",
    responses={422: {"model": Problem, "description": "`movement.*`"}},
)
async def create_movement(
    body: MovementIn, user: Cashier, movements: Movements, names: UserNames, clock: Today
) -> MovementOut:
    """Registra un ingreso o egreso; un egreso puede asociarse a un evento (CA-21.1, CA-21.2)."""
    entry = await RecordMovement(movements, clock)(body.to_request(user.id))
    return MovementOut.from_entry(entry, await names(user_ids([entry])))


@router.post(
    "/{movement_id}/void",
    operation_id="movements_void",
    responses={
        404: {"model": Problem, "description": "`movement.not_found`"},
        409: {"model": Problem, "description": "`movement.already_voided`"},
        422: {"model": Problem, "description": "`movement.reason_required`"},
    },
)
async def void_movement(
    movement_id: UUID,
    body: MovementVoidIn,
    user: Cashier,
    movements: Movements,
    names: UserNames,
    clock: Today,
) -> MovementOut:
    """Anula con motivo; queda el movimiento y su anulación, no se edita (CA-21.3, RN17)."""
    entry = await VoidMovement(movements, clock)(movement_id, reason=body.reason, voided_by=user.id)
    return MovementOut.from_entry(entry, await names(user_ids([entry])))
