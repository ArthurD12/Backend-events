"""Endpoints de cotizaciones (HU07–HU08). Traducen HTTP ⇄ caso de uso; sin reglas de negocio.

Exigen el permiso `quotes:manage` (administrador y encargado de eventos, DOMAIN.md §9).
"""

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteFilters,
)
from local_eventos.modules.commercial.application.quotes.use_cases.query_quotes import (
    MAX_PAGE_SIZE,
    ChangeQuoteStatus,
    GetQuote,
    SearchQuotes,
)
from local_eventos.modules.commercial.application.quotes.use_cases.save_quote import (
    CreateQuote,
    UpdateQuote,
)
from local_eventos.modules.commercial.domain.quotes.quote import Quote, QuoteStatus
from local_eventos.modules.commercial.presentation.dependencies import (
    Clients,
    Quotes,
    Services,
    Today,
)
from local_eventos.modules.commercial.presentation.quote_schemas import (
    QuoteIn,
    QuoteOut,
    QuotePageOut,
    QuoteStatusIn,
)
from local_eventos.modules.identity.public_api import CurrentUser, Permission, require_permission
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/quotes",
    tags=["cotizaciones"],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

_Responses = dict[int | str, dict[str, Any]]
SignedIn = Annotated[CurrentUser, Depends(require_permission(Permission.QUOTES_MANAGE))]

_NOT_FOUND: _Responses = {404: {"model": Problem, "description": "`quote.not_found`"}}
_SAVE: _Responses = {
    404: {"model": Problem, "description": "`quote.client_not_found`, `quote.service_not_found`"},
    409: {"model": Problem, "description": "`quote.client_inactive`, `quote.service_inactive`"},
    422: {"model": Problem, "description": "Dato inválido: `quote.event_date_past`, etc."},
}


@router.post("", status_code=status.HTTP_201_CREATED, operation_id="quotes_create", responses=_SAVE)
async def create_quote(
    body: QuoteIn,
    user: SignedIn,
    quotes: Quotes,
    clients: Clients,
    services: Services,
    clock: Today,
) -> QuoteOut:
    """Crea la cotización en borrador, con su código y su total calculado (HU07)."""
    quote = await CreateQuote(quotes, clients, services, clock)(
        body.to_command(), created_by=user.id
    )
    return await _out(quote, clients, clock.today())


@router.get("", operation_id="quotes_search")
async def search_quotes(
    _: SignedIn,
    quotes: Quotes,
    clock: Today,
    text: Annotated[str, Query(description="Parte del código o del nombre del cliente")] = "",
    client_id: UUID | None = None,
    status: QuoteStatus | None = None,
    event_date_from: date | None = None,
    event_date_to: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> QuotePageOut:
    """Busca por código, cliente, estado (incluida la vencida) y fecha del evento (CA-08.5)."""
    found = await SearchQuotes(quotes, clock)(
        QuoteFilters(
            text=text,
            client_id=client_id,
            status=status,
            event_date_from=event_date_from,
            event_date_to=event_date_to,
        ),
        page=page,
        page_size=page_size,
    )
    return QuotePageOut.from_page(found)


@router.get("/{quote_id}", operation_id="quotes_get", responses=_NOT_FOUND)
async def get_quote(
    quote_id: UUID, _: SignedIn, quotes: Quotes, clients: Clients, clock: Today
) -> QuoteOut:
    """La cotización completa, con sus líneas."""
    return await _out(await GetQuote(quotes)(quote_id), clients, clock.today())


@router.put(
    "/{quote_id}",
    operation_id="quotes_update",
    responses={
        **_SAVE,
        404: {"model": Problem, "description": "`quote.not_found` y los de `quotes_create`"},
        409: {"model": Problem, "description": "`quote.not_editable` y los de `quotes_create`"},
    },
)
async def update_quote(
    quote_id: UUID,
    body: QuoteIn,
    _: SignedIn,
    quotes: Quotes,
    clients: Clients,
    services: Services,
    clock: Today,
) -> QuoteOut:
    """Modifica una cotización en borrador (CA-08.1). Los precios ya congelados se mantienen."""
    quote = await UpdateQuote(quotes, clients, services, clock)(quote_id, body.to_command())
    return await _out(quote, clients, clock.today())


@router.post(
    "/{quote_id}/status",
    operation_id="quotes_change_status",
    responses={
        **_NOT_FOUND,
        409: {"model": Problem, "description": "`quote.invalid_transition`, `quote.expired`"},
    },
)
async def change_quote_status(
    quote_id: UUID, body: QuoteStatusIn, _: SignedIn, quotes: Quotes, clients: Clients, clock: Today
) -> QuoteOut:
    """Enviada, aceptada, rechazada o de vuelta a borrador (R-COT-3)."""
    quote = await ChangeQuoteStatus(quotes, clock)(quote_id, QuoteStatus(body.status))
    return await _out(quote, clients, clock.today())


async def _out(quote: Quote, clients: Clients, today: date) -> QuoteOut:
    client = await clients.get(quote.client_id)
    return QuoteOut.from_quote(quote, client_name=client.name if client else "", today=today)
