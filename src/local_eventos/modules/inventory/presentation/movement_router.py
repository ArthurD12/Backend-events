"""Endpoints de movimientos de almacén (HU23, HU26) y materiales por evento.

Registrar exige `inventory:manage`; quien registra queda como responsable (CA-26.1).
Ver los materiales de un evento exige `inventory:read`.
"""

from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from local_eventos.modules.identity.public_api import CurrentUser, Permission, require_permission
from local_eventos.modules.inventory.application.use_cases.event_materials import (
    GetEventMaterials,
)
from local_eventos.modules.inventory.application.use_cases.movements import (
    MovementCommand,
    RecordMovement,
)
from local_eventos.modules.inventory.domain.movement import MovementKind
from local_eventos.modules.inventory.presentation.dependencies import (
    Events,
    Movements,
    Products,
    Stock,
    Today,
)
from local_eventos.modules.inventory.presentation.schemas import (
    AdjustmentIn,
    EntryIn,
    EventMaterialOut,
    EventMovementIn,
    RecordedMovementOut,
    WasteIn,
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

Manager = Annotated[CurrentUser, Depends(require_permission(Permission.INVENTORY_MANAGE))]

_Responses = dict[int | str, dict[str, Any]]


def _responses(conflicts: str, not_found: str = "`inventory.product_not_found`") -> _Responses:
    return {
        404: {"model": Problem, "description": not_found},
        409: {"model": Problem, "description": conflicts},
        422: {"model": Problem, "description": "`inventory.validation`"},
    }


_EVENT_NOT_FOUND = "`inventory.product_not_found`, `inventory.event_not_found`"


class _Recorder:
    """Arma el caso de uso con las dependencias de la petición."""

    def __init__(
        self, products: Products, stock: Stock, movements: Movements, events: Events, clock: Today
    ) -> None:
        self._use_case = RecordMovement(products, stock, movements, events, clock)

    async def __call__(self, command: MovementCommand, user: CurrentUser) -> RecordedMovementOut:
        recorded = await self._use_case(command, recorded_by=user.id)
        return RecordedMovementOut.from_recorded(recorded)


Recorder = Annotated[_Recorder, Depends()]
_CREATED = status.HTTP_201_CREATED


@router.post(
    "/movements/entry",
    status_code=_CREATED,
    operation_id="inventory_movements_entry",
    responses=_responses("`inventory.product_inactive`"),
)
async def record_entry(body: EntryIn, user: Manager, record: Recorder) -> RecordedMovementOut:
    """CA-23.2: entrada con costo unitario y, si se conocen, proveedor, lote y vencimiento."""
    return await record(
        MovementCommand(
            kind=MovementKind.ENTRY,
            product_id=body.product_id,
            quantity=Decimal(body.quantity),
            occurred_on=body.occurred_on,
            unit_cost_cents=body.unit_cost_cents,
            supplier_id=body.supplier_id,
            lot=body.lot,
            expires_on=body.expires_on,
            reason=body.reason,
        ),
        user,
    )


@router.post(
    "/movements/exit",
    status_code=_CREATED,
    operation_id="inventory_movements_exit",
    responses=_responses(
        "`inventory.insufficient_stock`, `inventory.event_not_assignable`,"
        " `inventory.product_inactive`",
        _EVENT_NOT_FOUND,
    ),
)
async def record_exit(
    body: EventMovementIn, user: Manager, record: Recorder
) -> RecordedMovementOut:
    """CA-26.1 y CA-26.2: salida a un evento programado, confirmado o en ejecución."""
    return await record(_event_command(MovementKind.EXIT, body), user)


@router.post(
    "/movements/return",
    status_code=_CREATED,
    operation_id="inventory_movements_return",
    responses=_responses("`inventory.return_exceeds`", _EVENT_NOT_FOUND),
)
async def record_return(
    body: EventMovementIn, user: Manager, record: Recorder
) -> RecordedMovementOut:
    """CA-26.3: no supera lo que salió para el evento menos lo devuelto y lo perdido."""
    return await record(_event_command(MovementKind.RETURN, body), user)


@router.post(
    "/movements/waste",
    status_code=_CREATED,
    operation_id="inventory_movements_waste",
    responses=_responses(
        "`inventory.insufficient_stock`, `inventory.waste_exceeds`", _EVENT_NOT_FOUND
    ),
)
async def record_waste(body: WasteIn, user: Manager, record: Recorder) -> RecordedMovementOut:
    """CA-26.4: merma con motivo, de almacén (baja el stock) o de un evento."""
    return await record(
        MovementCommand(
            kind=MovementKind.WASTE,
            product_id=body.product_id,
            quantity=Decimal(body.quantity),
            occurred_on=body.occurred_on,
            event_id=body.event_id,
            reason=body.reason,
        ),
        user,
    )


@router.post(
    "/movements/adjustment",
    status_code=_CREATED,
    operation_id="inventory_movements_adjustment",
    responses=_responses("`inventory.insufficient_stock`"),
)
async def record_adjustment(
    body: AdjustmentIn, user: Manager, record: Recorder
) -> RecordedMovementOut:
    """R-INV-5: corrige el stock con un ajuste positivo o negativo y su motivo."""
    return await record(
        MovementCommand(
            kind=MovementKind.ADJUSTMENT,
            product_id=body.product_id,
            quantity=Decimal(body.quantity),
            occurred_on=body.occurred_on,
            reason=body.reason,
        ),
        user,
    )


@router.get(
    "/events/{event_id}/materials",
    dependencies=[Depends(require_permission(Permission.INVENTORY_READ))],
    operation_id="inventory_event_materials",
    responses={404: {"model": Problem, "description": "`inventory.event_not_found`"}},
)
async def event_materials(
    event_id: UUID, products: Products, movements: Movements, events: Events
) -> list[EventMaterialOut]:
    """CA-26.6: por producto, qué salió, qué volvió, qué se perdió y qué falta devolver."""
    lines = await GetEventMaterials(products, movements, events)(event_id)
    return [EventMaterialOut.from_line(line) for line in lines]


def _event_command(kind: MovementKind, body: EventMovementIn) -> MovementCommand:
    return MovementCommand(
        kind=kind,
        product_id=body.product_id,
        quantity=Decimal(body.quantity),
        occurred_on=body.occurred_on,
        event_id=body.event_id,
        reason=body.reason,
    )
