"""Forma de los datos de inventario en la API.

Las cantidades viajan como **texto decimal** (`"12.500"`), nunca como número de coma flotante:
así el frontend no pierde precisión. Las reglas las aplica el dominio (`inventory.validation`).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.inventory.application.use_cases.event_materials import (
    EventMaterialLine,
)
from local_eventos.modules.inventory.application.use_cases.movements import RecordedMovement
from local_eventos.modules.inventory.application.use_cases.products import (
    MovementPage,
    ProductView,
)
from local_eventos.modules.inventory.application.use_cases.recipes import RecipeView
from local_eventos.modules.inventory.application.use_cases.requirement import (
    EventRequirement,
    RequirementLine,
)
from local_eventos.modules.inventory.domain.movement import Movement, MovementKind
from local_eventos.modules.inventory.domain.product import Category, ProductKind, Unit
from local_eventos.modules.inventory.domain.recipe import RecipeBasis

CURRENCY = "PEN"

QuantityIn = Annotated[
    str,
    Field(
        pattern=r"^-?\d+(\.\d+)?$",
        description="Cantidad decimal como texto, hasta 3 decimales",
        examples=["12.5"],
    ),
]
PositiveQuantityIn = Annotated[
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


class ProductIn(BaseModel):
    code: str = Field(description="Único, se guarda en mayúsculas (máx. 20)")
    name: str
    category: Category
    unit: Unit
    kind: ProductKind = Field(description="CONSUMABLE (se gasta) o REUSABLE (vuelve)")
    min_stock: PositiveQuantityIn = "0"


class ProductOut(BaseModel):
    id: UUID
    code: str
    name: str
    category: Category
    unit: Unit
    kind: ProductKind
    min_stock: QuantityOut
    active: bool
    stock: QuantityOut
    avg_cost_cents: int = Field(description="Costo promedio ponderado por unidad (R-INV-3)")
    stock_value_cents: int
    currency: str
    is_low_stock: bool = Field(description="Stock ≤ mínimo (CA-23.5)")
    expiring_soon: bool = Field(description="Alguna entrada con stock vence en ≤ 15 días")
    next_expiry: date | None

    @classmethod
    def from_view(cls, view: ProductView) -> Self:
        product = view.product
        return cls(
            id=product.id,
            code=product.code,
            name=product.name,
            category=product.category,
            unit=product.unit,
            kind=product.kind,
            min_stock=quantity_text(product.min_stock),
            active=product.active,
            stock=quantity_text(view.stock),
            avg_cost_cents=view.avg_cost_cents,
            stock_value_cents=view.stock_value_cents,
            currency=CURRENCY,
            is_low_stock=view.is_low_stock,
            expiring_soon=view.expiring_soon,
            next_expiry=view.next_expiry,
        )


class EntryIn(BaseModel):
    product_id: UUID
    quantity: PositiveQuantityIn
    unit_cost_cents: int = Field(description="Costo unitario en céntimos: S/ 3.50 = 350")
    occurred_on: date | None = Field(default=None, description="Por defecto, hoy")
    supplier_id: UUID | None = None
    lot: str | None = None
    expires_on: date | None = None
    reason: str | None = Field(default=None, description="Observación opcional")


class EventMovementIn(BaseModel):
    """Salida o devolución de un evento."""

    product_id: UUID
    event_id: UUID
    quantity: PositiveQuantityIn
    occurred_on: date | None = None
    reason: str | None = Field(default=None, description="Observación opcional")


class WasteIn(BaseModel):
    product_id: UUID
    quantity: PositiveQuantityIn
    reason: str
    event_id: UUID | None = Field(
        default=None, description="Si se perdió en un evento: no baja el stock del almacén"
    )
    occurred_on: date | None = None


class AdjustmentIn(BaseModel):
    product_id: UUID
    quantity: QuantityIn = Field(description="Con signo: positivo suma, negativo resta")
    reason: str
    occurred_on: date | None = None


class MovementOut(BaseModel):
    id: UUID
    product_id: UUID
    kind: MovementKind
    quantity: QuantityOut = Field(description="Positiva; con signo solo en el ajuste")
    stock_delta: QuantityOut = Field(description="Cuánto cambió el stock del almacén")
    occurred_on: date
    event_id: UUID | None
    unit_cost_cents: int | None
    supplier_id: UUID | None
    lot: str | None
    expires_on: date | None
    reason: str | None
    purchase_id: UUID | None
    recorded_by: UUID
    recorded_at: datetime

    @classmethod
    def from_movement(cls, movement: Movement) -> Self:
        return cls(
            id=movement.id,
            product_id=movement.product_id,
            kind=movement.kind,
            quantity=quantity_text(movement.quantity),
            stock_delta=quantity_text(movement.stock_delta),
            occurred_on=movement.occurred_on,
            event_id=movement.event_id,
            unit_cost_cents=movement.unit_cost_cents,
            supplier_id=movement.supplier_id,
            lot=movement.lot,
            expires_on=movement.expires_on,
            reason=movement.reason,
            purchase_id=movement.purchase_id,
            recorded_by=movement.recorded_by,
            recorded_at=movement.recorded_at,
        )


class RecordedMovementOut(BaseModel):
    movement: MovementOut
    stock: QuantityOut = Field(description="Stock del producto después del movimiento")
    avg_cost_cents: int

    @classmethod
    def from_recorded(cls, recorded: RecordedMovement) -> Self:
        return cls(
            movement=MovementOut.from_movement(recorded.movement),
            stock=quantity_text(recorded.stock.quantity),
            avg_cost_cents=recorded.stock.avg_cost_cents,
        )


class MovementPageOut(BaseModel):
    items: list[MovementOut]
    total: int
    page: int
    page_size: int

    @classmethod
    def from_page(cls, page: MovementPage) -> Self:
        return cls(
            items=[MovementOut.from_movement(m) for m in page.items],
            total=page.total,
            page=page.page,
            page_size=page.page_size,
        )


class EventMaterialOut(BaseModel):
    product_id: UUID
    code: str
    name: str
    unit: Unit
    kind: ProductKind
    out: QuantityOut = Field(description="Salió para el evento")
    returned: QuantityOut = Field(description="Volvió al almacén")
    wasted: QuantityOut = Field(description="Se perdió o se dañó en el evento")
    pending_return: QuantityOut = Field(description="Reutilizable que falta devolver")

    @classmethod
    def from_line(cls, line: EventMaterialLine) -> Self:
        m = line.materials
        return cls(
            product_id=line.product.id,
            code=line.product.code,
            name=line.product.name,
            unit=line.product.unit,
            kind=line.product.kind,
            out=quantity_text(m.out),
            returned=quantity_text(m.returned),
            wasted=quantity_text(m.wasted),
            pending_return=quantity_text(m.pending_return),
        )


class RecipeLineIn(BaseModel):
    product_id: UUID
    quantity: PositiveQuantityIn = Field(description="En la unidad del producto (R-INV-1)")
    basis: RecipeBasis = Field(
        description="PER_PERSON: por invitado del evento. PER_SERVICE: por unidad contratada"
    )


class RecipeIn(BaseModel):
    lines: list[RecipeLineIn] = Field(description="Reemplaza todos los insumos del servicio")


class RecipeLineOut(BaseModel):
    product_id: UUID
    code: str
    name: str
    unit: Unit
    quantity: QuantityOut
    basis: RecipeBasis


class RecipeOut(BaseModel):
    service_id: UUID
    service_name: str
    lines: list[RecipeLineOut]

    @classmethod
    def from_view(cls, view: RecipeView) -> Self:
        return cls(
            service_id=view.service_id,
            service_name=view.service_name,
            lines=[
                RecipeLineOut(
                    product_id=product.id,
                    code=product.code,
                    name=product.name,
                    unit=product.unit,
                    quantity=quantity_text(line.quantity),
                    basis=line.basis,
                )
                for line, product in view.lines
            ],
        )


class RequirementLineOut(BaseModel):
    product_id: UUID
    code: str
    name: str
    unit: Unit
    required: QuantityOut = Field(description="Lo que piden los servicios contratados")
    out: QuantityOut = Field(description="Ya salió para el evento")
    reserved: QuantityOut = Field(description="Apartado para el evento")
    available: QuantityOut = Field(description="Libre en almacén (stock menos reservas vigentes)")
    shortage: QuantityOut = Field(
        description="Falta comprar: requerido - salido - reservado - disponible (mínimo 0)"
    )

    @classmethod
    def from_line(cls, line: RequirementLine) -> Self:
        return cls(
            product_id=line.product.id,
            code=line.product.code,
            name=line.product.name,
            unit=line.product.unit,
            required=quantity_text(line.required),
            out=quantity_text(line.out),
            reserved=quantity_text(line.reserved),
            available=quantity_text(line.available),
            shortage=quantity_text(line.shortage),
        )


class EventRequirementOut(BaseModel):
    event_id: UUID
    event_code: str
    guests: int
    calculated: bool = Field(
        description="Falso en eventos finalizados o cancelados: solo se ve lo que salió"
    )
    lines: list[RequirementLineOut]
    without_recipe: list[str] = Field(description="Servicios sin insumos definidos (CA-25.3)")

    @classmethod
    def from_requirement(cls, requirement: EventRequirement) -> Self:
        return cls(
            event_id=requirement.event_id,
            event_code=requirement.event_code,
            guests=requirement.guests,
            calculated=requirement.calculated,
            lines=[RequirementLineOut.from_line(line) for line in requirement.lines],
            without_recipe=requirement.without_recipe,
        )
