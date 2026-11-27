"""Forma de la ficha consolidada del evento en la API (HU14): un bloque por tema."""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.commercial.public_api import (
    ActivityInfo,
    ActivityStatus,
    ContractStatus,
    EventAccount,
    EventStatus,
    EventType,
    LineKind,
    LineUnit,
    NoteInfo,
)
from local_eventos.modules.inventory.public_api import EventMaterialInfo, ProductKind, Unit
from local_eventos.modules.ledger.public_api import PaymentKind, PaymentMethod
from local_eventos.modules.reporting.application.use_cases.event_sheet import EventSheet
from local_eventos.modules.staff.public_api import WorkerFunction

QuantityOut = str  # decimal con 3 decimales, como en inventory


def _quantity(value: Decimal) -> str:
    return f"{value:.3f}"


class SheetEventOut(BaseModel):
    id: UUID
    code: str
    status: EventStatus
    event_type: EventType
    event_date: date
    start_time: time
    end_time: time
    ends_next_day: bool
    venue: str
    guests: int
    coordinator_id: UUID
    coordinator_name: str | None = Field(description="Vacío si el usuario no existe")
    contract_id: UUID


class SheetClientOut(BaseModel):
    id: UUID
    name: str
    document_type: str
    document_number: str
    phone: str
    email: str | None


class SheetServiceOut(BaseModel):
    """Servicio contratado, sin precios (CA-14.2)."""

    kind: LineKind
    service_id: UUID | None
    description: str
    unit: LineUnit
    quantity: int


class SheetStaffOut(BaseModel):
    worker_id: UUID
    name: str
    role: str = Field(description="Función en el evento, legible")
    function: WorkerFunction
    function_description: str | None = Field(description="Solo con la función `OTHER`")
    starts_at: datetime
    ends_at: datetime


class SheetMaterialOut(BaseModel):
    product_id: UUID
    code: str
    name: str
    unit: Unit
    kind: ProductKind
    out: QuantityOut = Field(description="Salió para el evento (3 decimales)")
    returned: QuantityOut = Field(description="Volvió al almacén")
    wasted: QuantityOut = Field(description="Se perdió o se dañó en el evento")
    pending_return: QuantityOut = Field(description="Reutilizable que falta devolver")

    @classmethod
    def from_info(cls, info: EventMaterialInfo) -> Self:
        return cls(
            product_id=info.product.id,
            code=info.product.code,
            name=info.product.name,
            unit=info.product.unit,
            kind=info.product.kind,
            out=_quantity(info.out),
            returned=_quantity(info.returned),
            wasted=_quantity(info.wasted),
            pending_return=_quantity(info.pending_return),
        )


class SheetPaymentOut(BaseModel):
    id: UUID
    number: str
    kind: PaymentKind
    amount_cents: int
    method: PaymentMethod
    paid_on: date
    voided: bool = Field(description="Anulado: no cuenta en el saldo")


class SheetAccountOut(BaseModel):
    """CA-14.5: total, pagado, saldo, fecha límite y pagos del contrato."""

    contract_id: UUID
    contract_code: str
    contract_status: ContractStatus
    currency: str = "PEN"
    total_cents: int
    paid_cents: int = Field(description="Pagos vigentes (adelanto incluido)")
    refunded_cents: int
    balance_cents: int = Field(description="Saldo por cobrar (RN15)")
    balance_due_date: date
    overdue: bool
    payments: list[SheetPaymentOut]

    @classmethod
    def from_account(cls, account: EventAccount) -> Self:
        return cls(
            contract_id=account.contract_id,
            contract_code=account.contract_code,
            contract_status=account.contract_status,
            total_cents=account.total_cents,
            paid_cents=account.paid_cents,
            refunded_cents=account.refunded_cents,
            balance_cents=account.balance_cents,
            balance_due_date=account.balance_due_date,
            overdue=account.overdue,
            payments=[
                SheetPaymentOut(
                    id=p.id,
                    number=p.number,
                    kind=p.kind,
                    amount_cents=p.amount_cents,
                    method=p.method,
                    paid_on=p.paid_on,
                    voided=p.voided,
                )  # fmt: skip
                for p in account.payments
            ],
        )


class SheetActivityOut(BaseModel):
    id: UUID
    description: str
    status: ActivityStatus
    responsible_id: UUID
    responsible_name: str = Field(description="Vacío si el usuario no existe")
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_info(cls, info: ActivityInfo, names: dict[UUID, str]) -> Self:
        return cls(
            id=info.id,
            description=info.description,
            status=info.status,
            responsible_id=info.responsible_id,
            responsible_name=names.get(info.responsible_id, ""),
            created_at=info.created_at,
            completed_at=info.completed_at,
        )


class SheetNoteOut(BaseModel):
    id: UUID
    text: str
    created_by: UUID
    created_by_name: str = Field(description="Vacío si el usuario no existe")
    created_at: datetime
    edited_at: datetime | None

    @classmethod
    def from_info(cls, info: NoteInfo, names: dict[UUID, str]) -> Self:
        return cls(
            id=info.id,
            text=info.text,
            created_by=info.created_by,
            created_by_name=names.get(info.created_by, ""),
            created_at=info.created_at,
            edited_at=info.edited_at,
        )


class SheetFollowUpOut(BaseModel):
    """CA-14.6: actividades pendientes y completadas, y las últimas observaciones."""

    pending: list[SheetActivityOut] = Field(description="Por orden de creación")
    done: list[SheetActivityOut] = Field(description="Por orden de creación")
    recent_notes: list[SheetNoteOut] = Field(description="De la más reciente a la más antigua")


class EventSheetOut(BaseModel):
    event: SheetEventOut
    client: SheetClientOut
    services: list[SheetServiceOut]
    staff: list[SheetStaffOut] | None = Field(
        description="Personal designado (sin pago). `null` sin el permiso `staff_roster:read`"
    )
    materials: list[SheetMaterialOut] = Field(description="Por producto, ordenado por nombre")
    account: SheetAccountOut | None = Field(description="Vacío sin el permiso `payments:record`")
    follow_up: SheetFollowUpOut

    @classmethod
    def from_sheet(cls, sheet: EventSheet) -> Self:
        event, client, names = sheet.event, sheet.event.client, sheet.user_names
        activities = sheet.follow_up.activities
        return cls(
            event=SheetEventOut(
                id=event.id,
                code=event.code,
                status=event.status,
                event_type=event.event_type,
                event_date=event.event_date,
                start_time=event.start_time,
                end_time=event.end_time,
                ends_next_day=event.ends_next_day,
                venue=event.venue,
                guests=event.guests,
                coordinator_id=event.coordinator_id,
                coordinator_name=names.get(event.coordinator_id),
                contract_id=event.contract_id,
            ),  # fmt: skip
            client=SheetClientOut(
                id=client.id,
                name=client.name,
                document_type=client.document_type,
                document_number=client.document_number,
                phone=client.phone,
                email=client.email,
            ),  # fmt: skip
            services=[
                SheetServiceOut(
                    kind=s.kind,
                    service_id=s.service_id,
                    description=s.description,
                    unit=s.unit,
                    quantity=s.quantity,
                )  # fmt: skip
                for s in event.services
            ],
            staff=None
            if sheet.staff is None
            else [
                SheetStaffOut(
                    worker_id=s.worker_id,
                    name=s.worker_name,
                    role=s.role,
                    function=s.function,
                    function_description=s.function_description,
                    starts_at=s.starts_at,
                    ends_at=s.ends_at,
                )  # fmt: skip
                for s in sheet.staff
            ],
            materials=[SheetMaterialOut.from_info(m) for m in sheet.materials],
            account=SheetAccountOut.from_account(sheet.account) if sheet.account else None,
            follow_up=SheetFollowUpOut(
                pending=[
                    SheetActivityOut.from_info(a, names)
                    for a in activities
                    if a.status is ActivityStatus.PENDING
                ],
                done=[
                    SheetActivityOut.from_info(a, names)
                    for a in activities
                    if a.status is ActivityStatus.DONE
                ],
                recent_notes=[
                    SheetNoteOut.from_info(n, names) for n in sheet.follow_up.recent_notes
                ],
            ),
        )
