"""Ficha consolidada del evento (HU14). Con `events:read`; los pagos, solo con `payments:record`."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from local_eventos.modules.identity.public_api import CurrentUser, Permission, require_permission
from local_eventos.modules.reporting.application.use_cases.event_sheet import GetEventSheet
from local_eventos.modules.reporting.presentation.dependencies import (
    EventAccountDep,
    EventDetailDep,
    EventFollowUpDep,
    EventMaterialsDep,
    EventStaffDep,
    UserNamesDep,
)
from local_eventos.modules.reporting.presentation.sheet_schemas import EventSheetOut
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/reports",
    tags=["reportes"],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

Reader = Annotated[CurrentUser, Depends(require_permission(Permission.EVENTS_READ))]


@router.get(
    "/events/{event_id}/sheet",
    operation_id="reports_event_sheet",
    responses={404: {"model": Problem, "description": "`event.not_found`"}},
)
async def event_sheet(
    event_id: UUID,
    viewer: Reader,
    details: EventDetailDep,
    follow_up: EventFollowUpDep,
    materials: EventMaterialsDep,
    accounts: EventAccountDep,
    staff: EventStaffDep,
    names: UserNamesDep,
) -> EventSheetOut:
    """Evento, cliente, servicios, personal, materiales, pagos y seguimiento en una petición.

    Se arma en el momento con lo que cada módulo sabe (CA-14.7). `account` va vacío sin
    `payments:record` (CA-14.5); `staff` (personal designado, sin pago) va vacío sin
    `staff_roster:read` (025).
    """
    sheet = await GetEventSheet(details, follow_up, materials, accounts, staff, names)(
        event_id,
        include_account=Permission.PAYMENTS_RECORD in viewer.permissions,
        include_staff=Permission.STAFF_ROSTER_READ in viewer.permissions,
    )
    return EventSheetOut.from_sheet(sheet)
