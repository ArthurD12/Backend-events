"""Forma de los datos del personal en la API (lo que envía y recibe el frontend).

Solo describen la forma: los enums, el límite de la descripción y que los importes
sean céntimos enteros. Las reglas de negocio (nombre, documento, teléfono, función
«otro», condicional de hora extra…) las aplica el dominio y llegan como 422 con su
`staff.*` (plan §5.2/§5.3); aquí no se duplican.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.staff.application.ports.worker_repository import WorkerPage
from local_eventos.modules.staff.domain.document import DocumentType
from local_eventos.modules.staff.domain.enums import (
    WorkerFunction,
    WorkerStatus,
    WorkerType,
)
from local_eventos.modules.staff.domain.money import CURRENCY, Money
from local_eventos.modules.staff.domain.worker import Worker

# Céntimos: entero estricto (nunca decimales ni booleanos) y no negativo.
Cents = Annotated[int, Field(strict=True, ge=0)]
# Hora extra: si se informa, debe ser mayor que cero (forma del contrato).
OvertimeCents = Annotated[int, Field(strict=True, gt=0)]


class _WorkerEditable(BaseModel):
    """Campos editables de la ficha: `PUT` es reemplazo completo (plan §5.1)."""

    name: str = Field(description="Nombre completo del trabajador")
    document_type: DocumentType = Field(description="DNI o CE")
    document_number: str = Field(description="Número de documento; el dominio lo normaliza")
    phone: str | None = Field(default=None, description="Solo dígitos")
    function: WorkerFunction | None = Field(
        default=None, description="Función fija; OTHER exige descripción"
    )
    function_description: str | None = Field(
        default=None, max_length=120, description="Solo con la función OTHER"
    )
    worker_type: WorkerType | None = Field(default=None, description="FIXED o EVENTUAL")
    rate_cents: Cents | None = Field(
        default=None, description="Tarifa referencial en céntimos: S/ 45.00 = 4500"
    )
    overtime_applies: bool = Field(default=False, description="Si corresponde pago de hora extra")
    overtime_rate_cents: OvertimeCents | None = Field(
        default=None, description="Monto por hora extra en céntimos; obligatorio si aplica"
    )


class WorkerCreate(_WorkerEditable):
    """Cuerpo de `POST /v1/staff`: alta de un trabajador."""


class WorkerUpdate(_WorkerEditable):
    """Cuerpo de `PUT /v1/staff/{worker_id}`: reemplazo completo de los editables."""


class WorkerOut(BaseModel):
    """Ficha completa devuelta por la API, incluido el estado actual."""

    id: UUID
    name: str
    document_type: DocumentType
    document_number: str
    phone: str | None
    function: WorkerFunction | None
    function_description: str | None
    worker_type: WorkerType | None
    rate_cents: int | None
    overtime_applies: bool
    overtime_rate_cents: int | None
    status: WorkerStatus
    currency: Literal["PEN"]

    @classmethod
    def from_worker(cls, worker: Worker) -> Self:
        """Mapea el agregado de dominio a la respuesta de la API."""
        return cls(
            id=worker.id,
            name=worker.name,
            document_type=worker.document.type,
            document_number=worker.document.number,
            phone=worker.phone,
            function=worker.function,
            function_description=worker.function_description,
            worker_type=worker.worker_type,
            rate_cents=_cents_or_none(worker.rate),
            overtime_applies=worker.overtime_applies,
            overtime_rate_cents=_cents_or_none(worker.overtime_rate),
            status=worker.status,
            currency=CURRENCY,
        )


class WorkerSummaryOut(BaseModel):
    """Fila del listado: incluye el documento, que comparte el permiso `staff:manage`."""

    id: UUID
    name: str
    document_type: DocumentType
    document_number: str
    function: WorkerFunction | None
    function_description: str | None
    worker_type: WorkerType | None
    status: WorkerStatus

    @classmethod
    def from_worker(cls, worker: Worker) -> Self:
        return cls(
            id=worker.id,
            name=worker.name,
            document_type=worker.document.type,
            document_number=worker.document.number,
            function=worker.function,
            function_description=worker.function_description,
            worker_type=worker.worker_type,
            status=worker.status,
        )


class WorkerPageOut(BaseModel):
    """Página del listado con el total que cumple el filtro."""

    items: list[WorkerSummaryOut]
    total: int
    page: int
    page_size: int

    @classmethod
    def from_page(cls, page: WorkerPage) -> Self:
        return cls(
            items=[WorkerSummaryOut.from_worker(item) for item in page.items],
            total=page.total,
            page=page.page,
            page_size=page.page_size,
        )


def _cents_or_none(money: Money | None) -> int | None:
    return None if money is None else money.cents
