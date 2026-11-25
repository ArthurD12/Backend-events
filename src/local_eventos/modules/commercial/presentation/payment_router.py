"""Endpoints de un pago del contrato (HU19, HU20): anular y descargar su comprobante.

Exigen `payments:record` (administrador y encargado de eventos, R-CON-4).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from local_eventos.modules.commercial.application.contracts.use_cases.payments import (
    VoidContractPayment,
)
from local_eventos.modules.commercial.application.contracts.use_cases.receipt import (
    RenderPaymentReceipt,
)
from local_eventos.modules.commercial.presentation.contract_schemas import (
    ContractAccountOut,
    VoidIn,
)
from local_eventos.modules.commercial.presentation.dependencies import (
    Clients,
    Company,
    Contracts,
    Events,
    PaymentFind,
    PaymentHistory,
    PaymentVoid,
    ReceiptRenderer,
    Today,
    UserNames,
)
from local_eventos.modules.identity.public_api import CurrentUser, Permission, require_permission
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/payments",
    tags=["pagos"],
    dependencies=[Depends(require_permission(Permission.PAYMENTS_RECORD))],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
        404: {"model": Problem, "description": "`payment.not_found`"},
    },
)

Cashier = Annotated[CurrentUser, Depends(require_permission(Permission.PAYMENTS_RECORD))]


@router.post(
    "/{payment_id}/void",
    operation_id="payments_void",
    responses={
        409: {
            "model": Problem,
            "description": "`payment.not_voidable`, `payment.already_voided`",
        },
        422: {"model": Problem, "description": "`payment.reason_required`"},
    },
)
async def void_payment(
    payment_id: UUID,
    body: VoidIn,
    user: Cashier,
    contracts: Contracts,
    history: PaymentHistory,
    voider: PaymentVoid,
    names: UserNames,
    clock: Today,
) -> ContractAccountOut:
    """Anula un pago parcial con motivo; queda el pago y su anulación (CA-19.5, RN17)."""
    account = await VoidContractPayment(contracts, history, voider, clock)(
        payment_id, reason=body.reason, voided_by=user.id
    )
    ids = {e.payment.recorded_by for e in account.entries}
    ids |= {e.void.voided_by for e in account.entries if e.void}
    return ContractAccountOut.from_account(account, await names(ids))


@router.get(
    "/{payment_id}/receipt.pdf",
    operation_id="payments_receipt_pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "El comprobante"}},
)
async def payment_receipt(
    payment_id: UUID,
    finder: PaymentFind,
    history: PaymentHistory,
    contracts: Contracts,
    clients: Clients,
    events: Events,
    names: UserNames,
    renderer: ReceiptRenderer,
    company: Company,
    clock: Today,
) -> Response:
    """Comprobante interno del pago en PDF (HU20). Si está anulado, sale con la marca."""
    filename, content = await RenderPaymentReceipt(
        finder=finder,
        entries=history,
        contracts=contracts,
        clients=clients,
        events=events,
        names=names,
        renderer=renderer,
        company=company,
        clock=clock,
    )(payment_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
