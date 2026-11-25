"""Endpoints de eventos (HU10 y HU11). Consultar exige `events:read` (los tres roles);
convertir, planificar, avanzar estados y cancelar, `events:manage` (administrador y encargado
de eventos). Cancelar exige además `payments:record`, porque puede registrar una devolución."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from local_eventos.modules.commercial.application.contracts.use_cases.payments import balance_of
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventFilters,
)
from local_eventos.modules.commercial.application.events.use_cases.events import (
    CALENDAR_MAX_DAYS,
    MAX_PAGE_SIZE,
    CancelEvent,
    ConvertContractToEvent,
    EventCalendar,
    GetEvent,
    SearchEvents,
)
from local_eventos.modules.commercial.application.events.use_cases.planning import (
    ConfirmEvent,
    EventPlanning,
    FinishEvent,
    ListEventChanges,
    StartEvent,
    UpdateEventPlanning,
)
from local_eventos.modules.commercial.domain.events.event import Event, EventStatus
from local_eventos.modules.commercial.domain.quotes.quote import EventType
from local_eventos.modules.commercial.presentation.dependencies import (
    Clients,
    Contracts,
    Coordinators,
    Events,
    PaymentHistory,
    Payments,
    Quotes,
    Today,
    UserNames,
)
from local_eventos.modules.commercial.presentation.event_schemas import (
    CoordinatorOut,
    EventCancelIn,
    EventChangeOut,
    EventConvertIn,
    EventOut,
    EventPageOut,
    EventPlanningIn,
    EventPlanningOut,
    EventSummaryOut,
)
from local_eventos.modules.identity.public_api import CurrentUser, Permission, require_permission
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/events",
    tags=["eventos"],
    dependencies=[Depends(require_permission(Permission.EVENTS_READ))],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

Reader = Annotated[CurrentUser, Depends(require_permission(Permission.EVENTS_READ))]
Manager = Annotated[CurrentUser, Depends(require_permission(Permission.EVENTS_MANAGE))]
Cashier = Annotated[CurrentUser, Depends(require_permission(Permission.PAYMENTS_RECORD))]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    operation_id="events_convert",
    responses={
        404: {"model": Problem, "description": "`contract.not_found`"},
        409: {
            "model": Problem,
            "description": "`event.contract_not_ready`, `event.already_exists`",
        },
        422: {"model": Problem, "description": "`event.coordinator_invalid`"},
    },
)
async def convert_contract(
    body: EventConvertIn,
    user: Manager,
    events: Events,
    contracts: Contracts,
    quotes: Quotes,
    clients: Clients,
    coordinators: Coordinators,
    history: PaymentHistory,
    clock: Today,
) -> EventOut:
    """Convierte un contrato firmado y con adelanto en evento programado (HU10)."""
    event = await ConvertContractToEvent(events, contracts, quotes, coordinators, clock)(
        body.contract_id, created_by=user.id, coordinator_id=body.coordinator_id
    )
    return await _out(event, user, contracts, quotes, clients, coordinators, history)


@router.get("", operation_id="events_search")
async def search_events(
    events: Events,
    coordinators: Coordinators,
    text: Annotated[str, Query(description="Parte del código o del nombre del cliente")] = "",
    status: EventStatus | None = None,
    event_type: EventType | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> EventPageOut:
    """Eventos de la fecha más próxima a la más lejana."""
    found = await SearchEvents(events)(
        EventFilters(
            text=text,
            status=status,
            event_type=event_type,
            date_from=date_from,
            date_to=date_to,
        ),
        page=page,
        page_size=page_size,
    )
    return EventPageOut.from_page(found, {c.id: c.name for c in await coordinators()})


@router.get(
    "/calendar",
    operation_id="events_calendar",
    responses={422: {"model": Problem, "description": "`event.range_invalid`"}},
)
async def events_calendar(
    events: Events,
    coordinators: Coordinators,
    date_from: date,
    date_to: Annotated[date, Query(description=f"Hasta {CALENDAR_MAX_DAYS} días desde date_from")],
    text: Annotated[str, Query(description="Parte del código o del nombre del cliente")] = "",
    status: EventStatus | None = None,
    event_type: EventType | None = None,
) -> list[EventSummaryOut]:
    """HU12: todos los eventos del periodo visible del calendario, por fecha y hora."""
    found = await EventCalendar(events)(
        date_from, date_to, EventFilters(text=text, status=status, event_type=event_type)
    )
    names = {c.id: c.name for c in await coordinators()}
    return [EventSummaryOut.from_summary(item, names.get(item.coordinator_id)) for item in found]


@router.get("/coordinators", operation_id="events_coordinators")
async def list_coordinators(_: Manager, coordinators: Coordinators) -> list[CoordinatorOut]:
    """Usuarios activos que pueden coordinar un evento (R-EVT-2)."""
    return [CoordinatorOut(id=c.id, name=c.name) for c in await coordinators()]


@router.get(
    "/{event_id}",
    operation_id="events_get",
    responses={404: {"model": Problem, "description": "`event.not_found`"}},
)
async def get_event(
    event_id: UUID,
    viewer: Reader,
    events: Events,
    contracts: Contracts,
    quotes: Quotes,
    clients: Clients,
    coordinators: Coordinators,
    history: PaymentHistory,
) -> EventOut:
    """El evento; pagado y saldo solo para quien registra pagos (compras no ve dinero)."""
    event = await GetEvent(events)(event_id)
    return await _out(event, viewer, contracts, quotes, clients, coordinators, history)


@router.post(
    "/{event_id}/cancel",
    operation_id="events_cancel",
    responses={
        404: {"model": Problem, "description": "`event.not_found`"},
        409: {"model": Problem, "description": "`event.not_cancellable`"},
        422: {
            "model": Problem,
            "description": "`event.reason_required`, `contract.refund_invalid`, `payment.*`",
        },
    },
)
async def cancel_event(
    event_id: UUID,
    body: EventCancelIn,
    _: Manager,
    user: Cashier,
    events: Events,
    contracts: Contracts,
    payments: Payments,
    quotes: Quotes,
    clients: Clients,
    coordinators: Coordinators,
    history: PaymentHistory,
    clock: Today,
) -> EventOut:
    """Cancela el evento y anula su contrato; si hubo devolución, la registra (R-EVT-4)."""
    event = await CancelEvent(events, contracts, payments, clock)(
        event_id,
        reason=body.reason,
        cancelled_by=user.id,
        refund_cents=body.refund_cents,
        refund=body.refund.to_payment() if body.refund else None,
        note=body.note,
    )
    return await _out(event, user, contracts, quotes, clients, coordinators, history)


@router.put(
    "/{event_id}/planning",
    operation_id="events_planning_update",
    responses={
        404: {"model": Problem, "description": "`event.not_found`"},
        409: {"model": Problem, "description": "`event.not_editable`"},
        422: {
            "model": Problem,
            "description": "`event.date_past`, `event.time_invalid`, `event.guests_invalid`,"
            " `event.venue_required`, `event.venue_too_long`, `event.coordinator_invalid`",
        },
    },
)
async def update_planning(
    event_id: UUID,
    body: EventPlanningIn,
    user: Manager,
    events: Events,
    contracts: Contracts,
    quotes: Quotes,
    clients: Clients,
    coordinators: Coordinators,
    history: PaymentHistory,
    clock: Today,
) -> EventPlanningOut:
    """Edita fecha, horario, lugar, invitados y responsable en un evento programado o
    confirmado (CA-11.2, R-EVT-6). No cambia el contrato ni la cotización (R-EVT-7)."""
    result = await UpdateEventPlanning(events, coordinators, clock)(
        event_id,
        EventPlanning(
            event_date=body.event_date,
            start_time=body.start_time,
            end_time=body.end_time,
            venue=body.venue,
            guests=body.guests,
            coordinator_id=body.coordinator_id,
        ),
        by=user.id,
    )
    out = await _out(result.event, user, contracts, quotes, clients, coordinators, history)
    return EventPlanningOut(**out.model_dump(), warnings=list(result.warnings))


_TRANSITION_ERRORS: dict[int | str, dict[str, object]] = {
    404: {"model": Problem, "description": "`event.not_found`"},
    409: {"model": Problem, "description": "`event.invalid_transition`"},
}


@router.post("/{event_id}/confirm", operation_id="events_confirm", responses=_TRANSITION_ERRORS)
async def confirm_event(
    event_id: UUID,
    user: Manager,
    events: Events,
    contracts: Contracts,
    quotes: Quotes,
    clients: Clients,
    coordinators: Coordinators,
    history: PaymentHistory,
    clock: Today,
) -> EventOut:
    """Programado → confirmado (CA-11.4)."""
    event = await ConfirmEvent(events, clock)(event_id, by=user.id)
    return await _out(event, user, contracts, quotes, clients, coordinators, history)


@router.post(
    "/{event_id}/start",
    operation_id="events_start",
    responses={
        404: {"model": Problem, "description": "`event.not_found`"},
        409: {"model": Problem, "description": "`event.invalid_transition`, `event.not_event_day`"},
    },
)
async def start_event(
    event_id: UUID,
    user: Manager,
    events: Events,
    contracts: Contracts,
    quotes: Quotes,
    clients: Clients,
    coordinators: Coordinators,
    history: PaymentHistory,
    clock: Today,
) -> EventOut:
    """Confirmado → en ejecución, solo el día del evento en Lima; si cruza la medianoche,
    también el día siguiente (R-EVT-8, R-COT-1)."""
    event = await StartEvent(events, clock)(event_id, by=user.id)
    return await _out(event, user, contracts, quotes, clients, coordinators, history)


@router.post("/{event_id}/finish", operation_id="events_finish", responses=_TRANSITION_ERRORS)
async def finish_event(
    event_id: UUID,
    user: Manager,
    events: Events,
    contracts: Contracts,
    quotes: Quotes,
    clients: Clients,
    coordinators: Coordinators,
    history: PaymentHistory,
    clock: Today,
) -> EventOut:
    """En ejecución → finalizado; no exige saldo en cero (R-EVT-8)."""
    event = await FinishEvent(events, clock)(event_id, by=user.id)
    return await _out(event, user, contracts, quotes, clients, coordinators, history)


@router.get(
    "/{event_id}/changes",
    operation_id="events_changes_list",
    responses={404: {"model": Problem, "description": "`event.not_found`"}},
)
async def list_changes(event_id: UUID, events: Events, names: UserNames) -> list[EventChangeOut]:
    """Historial de planificación y estado, del más antiguo al más reciente (CA-11.5)."""
    changes = await ListEventChanges(events)(event_id)
    known = await names({c.changed_by for c in changes})
    return [EventChangeOut.from_change(c, known) for c in changes]


async def _out(
    event: Event,
    viewer: CurrentUser,
    contracts: Contracts,
    quotes: Quotes,
    clients: Clients,
    coordinators: Coordinators,
    history: PaymentHistory,
) -> EventOut:
    contract = await contracts.get(event.contract_id)
    balance = None
    if contract is not None and Permission.PAYMENTS_RECORD in viewer.permissions:
        balance = balance_of(contract, await history(contract.id))
    quote = await quotes.get(event.quote_id)
    client = await clients.get(event.client_id)
    names = {c.id: c.name for c in await coordinators()}
    return EventOut.from_event(
        event,
        contract=contract,
        quote_code=quote.code if quote else "",
        client_name=client.name if client else "",
        coordinator_name=names.get(event.coordinator_id),
        balance=balance,
    )
