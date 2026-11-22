"""Endpoints de contratos (HU41–HU42). Exigen `contracts:manage`; firmar y anular, además,
`payments:record` porque registran dinero (R-CON-4)."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractFilters,
)
from local_eventos.modules.commercial.application.contracts.use_cases.contracts import (
    MAX_PAGE_SIZE,
    CancelContract,
    GenerateContract,
    GetContract,
    SearchContracts,
    SignContract,
)
from local_eventos.modules.commercial.domain.contracts.contract import Contract, ContractStatus
from local_eventos.modules.commercial.presentation.contract_schemas import (
    ContractCancelIn,
    ContractGenerateIn,
    ContractOut,
    ContractPageOut,
    ContractSignIn,
)
from local_eventos.modules.commercial.presentation.dependencies import (
    Clients,
    Contracts,
    Events,
    PaymentHistory,
    Payments,
    Quotes,
    Today,
)
from local_eventos.modules.identity.public_api import CurrentUser, Permission, require_permission
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/contracts",
    tags=["contratos"],
    dependencies=[Depends(require_permission(Permission.CONTRACTS_MANAGE))],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

_Responses = dict[int | str, dict[str, Any]]
Manager = Annotated[CurrentUser, Depends(require_permission(Permission.CONTRACTS_MANAGE))]
Cashier = Annotated[CurrentUser, Depends(require_permission(Permission.PAYMENTS_RECORD))]
_NOT_FOUND: _Responses = {404: {"model": Problem, "description": "`contract.not_found`"}}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    operation_id="contracts_generate",
    responses={
        404: {"model": Problem, "description": "`contract.quote_not_found`"},
        409: {
            "model": Problem,
            "description": "`contract.quote_not_accepted`, `contract.already_exists`",
        },
        422: {"model": Problem, "description": "`contract.advance_invalid`"},
    },
)
async def generate_contract(
    body: ContractGenerateIn,
    user: Manager,
    contracts: Contracts,
    quotes: Quotes,
    clients: Clients,
    history: PaymentHistory,
    events: Events,
    clock: Today,
) -> ContractOut:
    """Genera el contrato de una cotización aceptada, pendiente de firma (HU41)."""
    contract = await GenerateContract(contracts, quotes, clock)(
        body.quote_id, created_by=user.id, advance_cents=body.advance_cents
    )
    return await _out(contract, quotes, clients, history, events)


@router.get("", operation_id="contracts_search")
async def search_contracts(
    contracts: Contracts,
    text: Annotated[str, Query(description="Parte del código o del nombre del cliente")] = "",
    status: ContractStatus | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> ContractPageOut:
    found = await SearchContracts(contracts)(
        ContractFilters(text=text, status=status), page=page, page_size=page_size
    )
    return ContractPageOut.from_page(found)


@router.get("/{contract_id}", operation_id="contracts_get", responses=_NOT_FOUND)
async def get_contract(
    contract_id: UUID,
    contracts: Contracts,
    quotes: Quotes,
    clients: Clients,
    history: PaymentHistory,
    events: Events,
) -> ContractOut:
    """El contrato con su firma, su anulación, sus pagos y su evento, si ya lo es."""
    contract = await GetContract(contracts)(contract_id)
    return await _out(contract, quotes, clients, history, events)


@router.post(
    "/{contract_id}/sign",
    operation_id="contracts_sign",
    responses={
        **_NOT_FOUND,
        409: {"model": Problem, "description": "`contract.not_pending`"},
        422: {"model": Problem, "description": "`contract.signer_required`, `payment.*`, etc."},
    },
)
async def sign_contract(
    contract_id: UUID,
    body: ContractSignIn,
    user: Cashier,
    contracts: Contracts,
    payments: Payments,
    quotes: Quotes,
    clients: Clients,
    history: PaymentHistory,
    events: Events,
    clock: Today,
) -> ContractOut:
    """Registra la firma y el pago del adelanto en un solo paso (HU42, R-CON-1)."""
    contract = await SignContract(contracts, payments, clock)(
        contract_id,
        signed_on=body.signed_on,
        signer_name=body.signer_name,
        advance=body.advance.to_payment(),
        recorded_by=user.id,
    )
    return await _out(contract, quotes, clients, history, events)


@router.post(
    "/{contract_id}/cancel",
    operation_id="contracts_cancel",
    responses={
        **_NOT_FOUND,
        409: {
            "model": Problem,
            "description": "`contract.already_cancelled`, `contract.has_event`",
        },
        422: {"model": Problem, "description": "`contract.reason_required`, etc."},
    },
)
async def cancel_contract(
    contract_id: UUID,
    body: ContractCancelIn,
    user: Cashier,
    contracts: Contracts,
    payments: Payments,
    quotes: Quotes,
    clients: Clients,
    history: PaymentHistory,
    events: Events,
    clock: Today,
) -> ContractOut:
    """Anula con motivo; si hubo devolución, se registra su monto (R-CON-3)."""
    contract = await CancelContract(contracts, payments, clock, events)(
        contract_id,
        reason=body.reason,
        cancelled_by=user.id,
        refund_cents=body.refund_cents,
        refund=body.refund.to_payment() if body.refund else None,
        note=body.note,
    )
    return await _out(contract, quotes, clients, history, events)


async def _out(
    contract: Contract,
    quotes: Quotes,
    clients: Clients,
    history: PaymentHistory,
    events: Events,
) -> ContractOut:
    quote = await quotes.get(contract.quote_id)
    client = await clients.get(contract.client_id)
    event = await events.get_by_contract(contract.id)
    return ContractOut.from_contract(
        contract,
        quote_code=quote.code if quote else "",
        client_name=client.name if client else "",
        payments=await history(contract.id),
        event_id=event.id if event else None,
    )
