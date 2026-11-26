"""Endpoints de compras (HU28, HU29) y faltantes. Exigen `purchasing:manage`."""

from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from local_eventos.modules.identity.public_api import CurrentUser, Permission, require_permission
from local_eventos.modules.purchasing.application.ports.repositories import PurchaseFilters
from local_eventos.modules.purchasing.application.use_cases.purchases import (
    MAX_PAGE_SIZE,
    CancelPurchase,
    CreatePurchaseFromEvent,
    CreatePurchaseRequest,
    GetPurchase,
    GetPurchaseDocument,
    ListPurchases,
    OrderPurchase,
    PurchaseDetailsBuilder,
    PurchaseRequestCommand,
    ReceivePurchase,
    RegisterPurchaseExpense,
    SuggestShortages,
)
from local_eventos.modules.purchasing.domain.errors import PurchasingValidationError
from local_eventos.modules.purchasing.domain.purchase import PurchaseStatus, ReceivedLine
from local_eventos.modules.purchasing.presentation.dependencies import (
    Company,
    Events,
    Expenses,
    LowStock,
    Products,
    Purchases,
    Receiver,
    Renderer,
    Requirement,
    Suppliers,
    Today,
)
from local_eventos.modules.purchasing.presentation.schemas import (
    CancelIn,
    ExpenseIn,
    OrderIn,
    PurchaseOut,
    PurchasePageOut,
    PurchaseRequestIn,
    ReceiveIn,
    ShortageOut,
)
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/purchasing",
    tags=["compras"],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

Manager = Annotated[CurrentUser, Depends(require_permission(Permission.PURCHASING_MANAGE))]
_MANAGE = [Depends(require_permission(Permission.PURCHASING_MANAGE))]

_Responses = dict[int | str, dict[str, Any]]
_NOT_FOUND: _Responses = {404: {"model": Problem, "description": "`purchasing.purchase_not_found`"}}
_INVALID: _Responses = {422: {"model": Problem, "description": "`purchasing.validation`"}}


def _transition(conflicts: str = "`purchasing.invalid_transition`") -> _Responses:
    return {**_NOT_FOUND, 409: {"model": Problem, "description": conflicts}, **_INVALID}


async def _detail(purchase_id: UUID, purchases: Purchases, products: Products,
                  suppliers: Suppliers) -> PurchaseOut:  # fmt: skip
    details = PurchaseDetailsBuilder(products, suppliers)
    return PurchaseOut.from_details(await GetPurchase(purchases, details)(purchase_id))


@router.get("/shortages", dependencies=_MANAGE, operation_id="purchasing_shortages")
async def shortages(low_stock: LowStock) -> list[ShortageOut]:
    """CA-28.2 ("Agregar faltantes"): productos con stock bajo y cuánto pedir."""
    return [ShortageOut.from_shortage(s) for s in await SuggestShortages(low_stock)()]


@router.get("/purchases", dependencies=_MANAGE, operation_id="purchasing_purchases_list")
async def list_purchases(
    purchases: Purchases,
    products: Products,
    suppliers: Suppliers,
    status: PurchaseStatus | None = None,
    event_id: UUID | None = None,
    supplier_id: UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> PurchasePageOut:
    """De la más reciente a la más antigua."""
    found = await ListPurchases(purchases, PurchaseDetailsBuilder(products, suppliers))(
        PurchaseFilters(status=status, event_id=event_id, supplier_id=supplier_id),
        page=page,
        page_size=page_size,
    )
    return PurchasePageOut.from_page(found)


@router.post(
    "/purchases",
    status_code=status.HTTP_201_CREATED,
    operation_id="purchasing_purchases_create",
    responses=_INVALID,
)
async def create_purchase(
    body: PurchaseRequestIn,
    user: Manager,
    purchases: Purchases,
    products: Products,
    suppliers: Suppliers,
    clock: Today,
) -> PurchaseOut:
    """CA-28.1: solicitud de compra con sus líneas; se puede vincular a un evento."""
    purchase = await CreatePurchaseRequest(purchases, products, clock)(
        PurchaseRequestCommand(
            lines=[(line.product_id, Decimal(line.quantity)) for line in body.lines],
            event_id=body.event_id,
            notes=body.notes,
        ),
        created_by=user.id,
    )
    return await _detail(purchase.id, purchases, products, suppliers)


@router.get(
    "/purchases/{purchase_id}",
    dependencies=_MANAGE,
    operation_id="purchasing_purchases_get",
    responses=_NOT_FOUND,
)
async def get_purchase(
    purchase_id: UUID, purchases: Purchases, products: Products, suppliers: Suppliers
) -> PurchaseOut:
    return await _detail(purchase_id, purchases, products, suppliers)


@router.post(
    "/purchases/{purchase_id}/order",
    operation_id="purchasing_purchases_order",
    responses={
        **_transition("`purchasing.invalid_transition`, `purchasing.supplier_inactive`"),
        404: {
            "model": Problem,
            "description": "`purchasing.purchase_not_found`, `purchasing.supplier_not_found`",
        },
    },
)
async def order_purchase(
    purchase_id: UUID,
    body: OrderIn,
    user: Manager,
    purchases: Purchases,
    products: Products,
    suppliers: Suppliers,
    clock: Today,
) -> PurchaseOut:
    """CA-29.1: elige proveedor y costo unitario de cada línea."""
    if len({line.product_id for line in body.lines}) != len(body.lines):
        raise PurchasingValidationError("Un producto aparece dos veces.")
    await OrderPurchase(purchases, suppliers, clock)(
        purchase_id,
        supplier_id=body.supplier_id,
        unit_costs={line.product_id: line.unit_cost_cents for line in body.lines},
        ordered_by=user.id,
    )
    return await _detail(purchase_id, purchases, products, suppliers)


@router.post(
    "/purchases/{purchase_id}/receive",
    operation_id="purchasing_purchases_receive",
    responses=_transition(),
)
async def receive_purchase(
    purchase_id: UUID,
    body: ReceiveIn,
    user: Manager,
    purchases: Purchases,
    products: Products,
    suppliers: Suppliers,
    receiver: Receiver,
    clock: Today,
) -> PurchaseOut:
    """CA-29.2 y CA-29.3: una sola vez; registra las entradas al almacén con costo y proveedor."""
    await ReceivePurchase(purchases, receiver, clock)(
        purchase_id,
        lines=[
            ReceivedLine(
                product_id=line.product_id,
                quantity=Decimal(line.received_quantity),
                lot=line.lot,
                expires_on=line.expires_on,
            )
            for line in body.lines
        ],
        received_by=user.id,
        invoice_number=body.invoice_number,
        received_on=body.received_on,
    )
    return await _detail(purchase_id, purchases, products, suppliers)


@router.post(
    "/purchases/{purchase_id}/cancel",
    operation_id="purchasing_purchases_cancel",
    responses=_transition(),
)
async def cancel_purchase(
    purchase_id: UUID,
    body: CancelIn,
    user: Manager,
    purchases: Purchases,
    products: Products,
    suppliers: Suppliers,
    clock: Today,
) -> PurchaseOut:
    """Cancela una compra solicitada u ordenada, con motivo."""
    await CancelPurchase(purchases, clock)(purchase_id, reason=body.reason, cancelled_by=user.id)
    return await _detail(purchase_id, purchases, products, suppliers)


@router.post(
    "/purchases/from-event/{event_id}",
    status_code=status.HTTP_201_CREATED,
    operation_id="purchasing_purchases_from_event",
    responses={
        404: {"model": Problem, "description": "`purchasing.event_not_found`"},
        409: {"model": Problem, "description": "`purchasing.no_shortages`"},
        422: {"model": Problem, "description": "`purchasing.validation`"},
    },
)
async def create_purchase_from_event(
    event_id: UUID,
    user: Manager,
    purchases: Purchases,
    products: Products,
    suppliers: Suppliers,
    requirement: Requirement,
    clock: Today,
) -> PurchaseOut:
    """CA-25.6: solicitud con los faltantes del requerimiento, vinculada al evento."""
    create = CreatePurchaseRequest(purchases, products, clock)
    purchase = await CreatePurchaseFromEvent(create, requirement)(event_id, created_by=user.id)
    return await _detail(purchase.id, purchases, products, suppliers)


@router.get(
    "/purchases/{purchase_id}/pdf",
    dependencies=_MANAGE,
    operation_id="purchasing_purchases_pdf",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "La orden de compra en PDF"},
        **_NOT_FOUND,
    },
)
async def purchase_pdf(
    purchase_id: UUID,
    purchases: Purchases,
    products: Products,
    suppliers: Suppliers,
    events: Events,
    renderer: Renderer,
    company: Company,
) -> Response:
    """CA-30.2: descarga la compra como orden de compra en PDF. No la modifica."""
    details = PurchaseDetailsBuilder(products, suppliers)
    filename, content = await GetPurchaseDocument(purchases, details, events, renderer, company)(
        purchase_id
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/purchases/{purchase_id}/expense",
    dependencies=[Depends(require_permission(Permission.PAYMENTS_RECORD))],
    operation_id="purchasing_purchases_expense",
    responses={
        **_NOT_FOUND,
        403: {
            "model": Problem,
            "description": "`auth.forbidden` (exige también `payments:record`)",
        },
        409: {
            "model": Problem,
            "description": "`purchasing.expense_not_available`,"
            " `purchasing.expense_already_registered`",
        },
    },
)
async def register_expense(
    purchase_id: UUID,
    body: ExpenseIn,
    user: Manager,
    purchases: Purchases,
    products: Products,
    suppliers: Suppliers,
    expenses: Expenses,
    clock: Today,
) -> PurchaseOut:
    """CA-30.3 y R-COM-3: egreso de insumos por el total de la compra recibida, una sola vez."""
    await RegisterPurchaseExpense(purchases, expenses, clock)(
        purchase_id, method=body.method, reference=body.reference, recorded_by=user.id
    )
    return await _detail(purchase_id, purchases, products, suppliers)
