"""Forma de los datos de compras en la API. Cantidades como texto decimal; costos en céntimos."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.inventory.public_api import Unit
from local_eventos.modules.purchasing.application.use_cases.purchases import (
    PurchaseDetails,
    PurchasePage,
    Shortage,
)
from local_eventos.modules.purchasing.domain.purchase import CURRENCY, PurchaseStatus
from local_eventos.modules.purchasing.domain.supplier import DocumentType, Supplier

QuantityIn = Annotated[
    str,
    Field(
        pattern=r"^\d+(\.\d+)?$",
        description="Cantidad sin signo como texto, hasta 3 decimales",
        examples=["12.5"],
    ),
]
QuantityOut = Annotated[
    str, Field(description="Cantidad decimal con 3 decimales", examples=["12.500"])
]


def quantity_text(value: Decimal) -> str:
    return f"{value:.3f}"


class SupplierIn(BaseModel):
    name: str = Field(description="Razón social")
    document_type: DocumentType
    document_number: str = Field(description="RUC de 11 dígitos o DNI de 8")
    phone: str
    contact_name: str | None = None
    email: str | None = None
    address: str | None = None


class SupplierOut(BaseModel):
    id: UUID
    name: str
    document_type: DocumentType
    document_number: str
    phone: str
    contact_name: str | None
    email: str | None
    address: str | None
    active: bool

    @classmethod
    def from_supplier(cls, s: Supplier) -> Self:
        return cls(
            id=s.id, name=s.name, document_type=s.document_type,
            document_number=s.document_number, phone=s.phone, contact_name=s.contact_name,
            email=s.email, address=s.address, active=s.active,
        )  # fmt: skip


class RequestLineIn(BaseModel):
    product_id: UUID
    quantity: QuantityIn


class PurchaseRequestIn(BaseModel):
    lines: list[RequestLineIn]
    event_id: UUID | None = Field(default=None, description="Evento para el que se compra")
    notes: str | None = None


class OrderLineIn(BaseModel):
    product_id: UUID
    unit_cost_cents: int = Field(description="Costo unitario en céntimos: S/ 3.50 = 350")


class OrderIn(BaseModel):
    supplier_id: UUID
    lines: list[OrderLineIn]


class ReceiveLineIn(BaseModel):
    product_id: UUID
    received_quantity: QuantityIn = Field(description="Cantidad que llegó (puede ser 0)")
    lot: str | None = None
    expires_on: date | None = None


class ReceiveIn(BaseModel):
    lines: list[ReceiveLineIn] = Field(description="Todas las líneas de la compra (R-COM-2)")
    invoice_number: str | None = Field(default=None, description="Factura o boleta del proveedor")
    received_on: date | None = Field(default=None, description="Por defecto, hoy")


class CancelIn(BaseModel):
    reason: str


class PurchaseLineOut(BaseModel):
    product_id: UUID
    product_code: str | None
    product_name: str | None
    unit: Unit | None
    quantity: QuantityOut
    unit_cost_cents: int | None
    received_quantity: QuantityOut | None
    lot: str | None
    expires_on: date | None
    total_cents: int | None


class PurchaseOut(BaseModel):
    id: UUID
    code: str
    status: PurchaseStatus
    event_id: UUID | None
    notes: str | None
    supplier_id: UUID | None
    supplier_name: str | None
    invoice_number: str | None
    lines: list[PurchaseLineOut]
    total_cents: int | None = Field(description="Pedido al ordenar; real al recibir")
    currency: str
    created_by: UUID
    created_at: datetime
    ordered_at: datetime | None
    received_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None

    @classmethod
    def from_details(cls, details: PurchaseDetails) -> Self:
        p = details.purchase
        lines = []
        for line in p.lines:
            info = details.products.get(line.product_id)
            lines.append(
                PurchaseLineOut(
                    product_id=line.product_id,
                    product_code=info.code if info else None,
                    product_name=info.name if info else None,
                    unit=info.unit if info else None,
                    quantity=quantity_text(line.quantity),
                    unit_cost_cents=line.unit_cost_cents,
                    received_quantity=None
                    if line.received_quantity is None
                    else quantity_text(line.received_quantity),
                    lot=line.lot,
                    expires_on=line.expires_on,
                    total_cents=line.total_cents,
                )
            )
        return cls(
            id=p.id,
            code=p.code,
            status=p.status,
            event_id=p.event_id,
            notes=p.notes,
            supplier_id=p.supplier_id,
            supplier_name=details.supplier.name if details.supplier else None,
            invoice_number=p.invoice_number,
            lines=lines,
            total_cents=p.total_cents,
            currency=CURRENCY,
            created_by=p.created.by,
            created_at=p.created.at,
            ordered_at=p.ordered.at if p.ordered else None,
            received_at=p.received.at if p.received else None,
            cancelled_at=p.cancelled.at if p.cancelled else None,
            cancel_reason=p.cancel_reason,
        )


class PurchasePageOut(BaseModel):
    items: list[PurchaseOut]
    total: int
    page: int
    page_size: int

    @classmethod
    def from_page(cls, page: PurchasePage) -> Self:
        return cls(
            items=[PurchaseOut.from_details(d) for d in page.items],
            total=page.total,
            page=page.page,
            page_size=page.page_size,
        )


class ShortageOut(BaseModel):
    product_id: UUID
    code: str
    name: str
    unit: Unit
    stock: QuantityOut
    min_stock: QuantityOut
    suggested_quantity: QuantityOut = Field(description="Para volver al mínimo; editable")

    @classmethod
    def from_shortage(cls, s: Shortage) -> Self:
        return cls(
            product_id=s.product.id, code=s.product.code, name=s.product.name,
            unit=s.product.unit, stock=quantity_text(s.stock),
            min_stock=quantity_text(s.min_stock),
            suggested_quantity=quantity_text(s.suggested_quantity),
        )  # fmt: skip
